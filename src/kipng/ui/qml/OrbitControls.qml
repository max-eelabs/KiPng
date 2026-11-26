// Copyright (c) 2026 Maxim Pavlov
// SPDX-License-Identifier: GPL-3.0-or-later

import QtQuick
import QtQuick3D

MouseArea {
    required property Node pivot
    required property PerspectiveCamera camera
    required property real boardRadius
    required property real verticalHalfAngle
    property vector3d angles: Qt.vector3d(-55, -25, 0)
    property point previousPosition

    function wrapAngle(angle: real): real {
        return ((angle % 360) + 360) % 360
    }

    function orbit(dx: real, dy: real) {
        // Keep the drag angles through both poles instead of reading Euler angles back from Qt.
        angles = Qt.vector3d(wrapAngle(angles.x - dy * 0.35), wrapAngle(angles.y - dx * 0.35), 0)
    }

    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
    onPressed: mouse => previousPosition = Qt.point(mouse.x, mouse.y)

    onPositionChanged: mouse => {
        if (!pressed)
            return

        const dx = mouse.x - previousPosition.x
        const dy = mouse.y - previousPosition.y
        previousPosition = Qt.point(mouse.x, mouse.y)


        if (mouse.modifiers & Qt.ControlModifier) {
            // Translate in screen space at the current distance from the board.
            const scale = 2 * camera.z * Math.tan(verticalHalfAngle) / height
            const movement = pivot.right.times(-dx * scale).plus(pivot.up.times(dy * scale))
            pivot.position = pivot.position.plus(movement)
            return
        }
        orbit(dx, dy)
    }

    onWheel: wheel => {
        const delta = wheel.angleDelta.y || wheel.pixelDelta.y
        const distance = camera.z * Math.exp(-delta / 700)
        camera.z = Math.max(boardRadius * 0.3, Math.min(boardRadius * 30, distance))
    }
}
