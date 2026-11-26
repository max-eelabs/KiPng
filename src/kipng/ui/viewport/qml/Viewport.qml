// Copyright (c) 2026 Maxim Pavlov
// SPDX-License-Identifier: GPL-3.0-or-later

import QtQuick
import QtQuick.Effects
import QtQuick3D
import QtQuick3D.AssetUtils
import QtQuick3D.Helpers

Rectangle {
    id: viewport

    property url modelSource
    property vector2d defaultAngles
    property var featureSources: []
    property real renderAspectRatio: 9 / 16
    property bool renderFrameVisible: false
    property bool captureMode: false
    readonly property real renderFrameInset: captureMode ? 0 : 16
    readonly property real renderFrameWidth: Math.min(
        Math.max(0, width - 2 * renderFrameInset),
        Math.max(0, height - 2 * renderFrameInset) * renderAspectRatio
    )
    readonly property real renderFrameHeight: renderFrameWidth / renderAspectRatio

    property vector3d boardCenter
    property real boardRadius: 0
    property vector3d boardExtent
    readonly property real boardSpan: Math.max(boardExtent.x, boardExtent.z)
    readonly property bool framed: boardRadius > 0
    readonly property real verticalHalfAngle: boardCamera.fieldOfView * Math.PI / 360
    readonly property vector3d cameraAngles: orbitControls.angles
    readonly property real cameraDistance: boardCamera.boardDepth
    readonly property vector2d cameraPan: {
        const offset = cameraPivot.position.minus(boardCenter)
        return Qt.vector2d(offset.dotProduct(cameraPivot.right), offset.dotProduct(cameraPivot.up))
    }
    readonly property real frameHalfWidth:
        cameraDistance * Math.tan(verticalHalfAngle) * renderFrameWidth / Math.max(height, 1)

    signal loadFailed(string message)

    function fitBoard() {
        if (!framed)
            return

        cameraPivot.position = boardCenter
        const frameSpan = Math.min(renderFrameWidth, renderFrameHeight)
        const halfAngle = Math.atan(Math.tan(verticalHalfAngle) * frameSpan / Math.max(height, 1))
        boardCamera.z = 1.1 * boardRadius / Math.sin(Math.max(halfAngle, 0.01))
    }

    function viewAngles(pitch: real, yaw: real, alignLongAxis: bool): vector3d {
        // The preset assumes Z is the long axis. Turn a wider board a quarter turn.
        const quarterTurn = alignLongAxis && boardExtent.x > boardExtent.z ? 90 : 0
        return Qt.vector3d(pitch, yaw + quarterTurn, 0)
    }

    function setCameraView(pitch: real, yaw: real, alignLongAxis: bool) {
        orbitControls.angles = viewAngles(pitch, yaw, alignLongAxis)
        fitBoard()
    }

    function setRenderCamera(
        pitch: real, yaw: real, distance: real, panX: real, panY: real, halfWidth: real
    ) {
        orbitControls.angles = Qt.vector3d(pitch, yaw, 0)
        const pan = cameraPivot.right.times(panX).plus(cameraPivot.up.times(panY))
        cameraPivot.position = boardCenter.plus(pan)
        boardCamera.z = distance
        // Narrow the field of view to fill the capture with the original crop.
        boardCamera.fieldOfView = 360 / Math.PI * Math.atan(halfWidth / distance / renderAspectRatio)
    }

    color: "white"
    clip: true

    View3D {
        anchors.fill: parent
        camera: boardCamera
        layer.enabled: true
        layer.effect: MultiEffect {
            // Scale and offset the projected silhouette like the PNG render.
            readonly property real imageScale:
                Math.min(viewport.renderFrameWidth, viewport.renderFrameHeight) / 1080
            readonly property real pixelsPerUnit: viewport.cameraDistance > 0
                ? viewport.height / (2 * viewport.cameraDistance * Math.tan(viewport.verticalHalfAngle))
                : 0

            autoPaddingEnabled: false
            blurMax: 24
            shadowEnabled: true
            shadowScale: 1.08
            shadowBlur: Math.min(1, imageScale)
            shadowOpacity: 0.31
            shadowHorizontalOffset: 3 * imageScale
                + viewport.cameraPan.x * pixelsPerUnit * (shadowScale - 1)
            shadowVerticalOffset: 20 * imageScale
                - viewport.cameraPan.y * pixelsPerUnit * (shadowScale - 1)
        }
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.Medium
            specularAAEnabled: true
            lightProbe: Texture {
                textureData: ProceduralSkyTextureData {
                    textureQuality: ProceduralSkyTextureData.SkyTextureQualityLow
                    skyTopColor: "#e6e6e6"
                    skyHorizonColor: "#b3b3b3"
                    groundHorizonColor: "#b3b3b3"
                    groundBottomColor: "#e6e6e6"
                    sunEnergy: 0
                }
            }
        }

        Node {
            id: cameraPivot
            eulerRotation: viewport.cameraAngles

            PerspectiveCamera {
                id: boardCamera
                fieldOfView: 42

                // Fit the depth range to the board to keep thin surface layers separate.
                readonly property real boardDepth:
                    viewport.boardCenter.minus(scenePosition).dotProduct(forward)
                clipNear: viewport.framed
                    ? Math.max(viewport.boardRadius / 1000, boardDepth - 1.2 * viewport.boardRadius)
                    : 0.001
                clipFar: viewport.framed
                    ? Math.max(
                        clipNear + viewport.boardRadius,
                        boardDepth + 1.2 * viewport.boardRadius
                    )
                    : 100

                DirectionalLight {
                    brightness: 1
                }
            }
        }

        DirectionalLight {
            // Light the face toward the camera along its board normal.
            eulerRotation.x: boardCamera.forward.y <= 0 ? -90 : 90
            brightness: 0.2
        }

        RuntimeLoader {
            id: boardModel
            source: viewport.modelSource

            onStatusChanged: {
                if (status === RuntimeLoader.Error)
                    viewport.loadFailed(qsTr("Could not open the 3D model.\n\n%1").arg(errorString))
            }

            onBoundsChanged: {
                if (viewport.framed)
                    return

                const extent = bounds.maximum.minus(bounds.minimum)
                const radius = extent.length() / 2
                if (radius <= 0)
                    return

                viewport.boardCenter = bounds.minimum.plus(extent.times(0.5))
                // The GLB board plane is XZ, with +Y pointing out of the top copper.
                viewport.boardExtent = extent
                viewport.boardRadius = radius
                viewport.fitBoard()
            }
        }
    }

    OrbitControls {
        id: orbitControls
        objectName: "orbitControls"
        angles: viewport.viewAngles(viewport.defaultAngles.x, viewport.defaultAngles.y, true)
        anchors.fill: parent
        enabled: viewport.framed
        pivot: cameraPivot
        camera: boardCamera
        boardRadius: viewport.boardRadius
        verticalHalfAngle: viewport.verticalHalfAngle
    }

    Repeater {
        model: viewport.framed ? viewport.featureSources : []
        Loader {
            required property url modelData
            anchors.fill: parent
            Component.onCompleted: setSource(modelData, { viewport: viewport })
        }
    }
}
