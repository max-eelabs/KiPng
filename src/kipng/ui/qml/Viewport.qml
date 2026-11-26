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

    // Fit the board for the expanded viewport even while the compact loader is visible.
    property real framingAspect: width / Math.max(height, 1)
    property vector3d boardCenter
    property real boardRadius: 0
    property real boardSpan: 0
    readonly property bool framed: boardRadius > 0
    readonly property real verticalHalfAngle: boardCamera.fieldOfView * Math.PI / 360
    readonly property vector3d cameraAngles: orbitControls.angles
    readonly property real cameraDistance: boardCamera.boardDepth
    readonly property vector2d cameraPan: {
        const offset = cameraPivot.position.minus(boardCenter)
        return Qt.vector2d(offset.dotProduct(cameraPivot.right), offset.dotProduct(cameraPivot.up))
    }
    readonly property real frameHalfWidth:
        cameraDistance * Math.tan(verticalHalfAngle) * Math.min(1, width / Math.max(height, 1))

    signal loadFailed(string message)

    color: "white"
    clip: true

    View3D {
        anchors.fill: parent
        camera: boardCamera
        layer.enabled: true
        layer.effect: MultiEffect {
            // Scale and offset the projected silhouette like the portrait render.
            readonly property real imageScale: Math.min(viewport.width, viewport.height) / 1080
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
                viewport.boardSpan = Math.max(extent.x, extent.z)
                cameraPivot.position = viewport.boardCenter
                const horizontalHalfAngle = Math.atan(
                    Math.tan(viewport.verticalHalfAngle) * viewport.framingAspect
                )
                const halfAngle = Math.min(viewport.verticalHalfAngle, horizontalHalfAngle)
                boardCamera.z = 1.1 * radius / Math.sin(Math.max(halfAngle, 0.01))
                viewport.boardRadius = radius
            }
        }
    }

    OrbitControls {
        id: orbitControls
        objectName: "orbitControls"
        anchors.fill: parent
        enabled: viewport.framed
        pivot: cameraPivot
        camera: boardCamera
        boardRadius: viewport.boardRadius
        verticalHalfAngle: viewport.verticalHalfAngle
    }
}
