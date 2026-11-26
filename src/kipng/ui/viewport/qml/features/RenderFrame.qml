// Copyright (c) 2026 Maxim Pavlov
// SPDX-License-Identifier: GPL-3.0-or-later

import QtQuick
import QtQuick.Window

Item {
    id: guide
    objectName: "renderFrame"

    required property Item viewport
    visible: viewport.renderFrameVisible

    readonly property color markColor: "#737373"
    readonly property real pixelRatio: Screen.devicePixelRatio
    readonly property real strokeWidth: snapToPixel(2)

    // Align the strokes to physical pixels so their weight survives fractional crop sizes.
    function snapToPixel(value: real): real {
        return Math.round(value * pixelRatio) / pixelRatio
    }

    Item {
        id: frame

        anchors.centerIn: parent
        anchors.alignWhenCentered: false
        width: guide.viewport.renderFrameWidth
        height: guide.viewport.renderFrameHeight

        Repeater {
            model: 4

            Item {
                id: corner

                required property int index
                readonly property bool rightEdge: index % 2 === 1
                readonly property bool bottomEdge: index >= 2

                x: guide.snapToPixel(frame.x + (rightEdge ? frame.width : 0))
                    - frame.x - (rightEdge ? width : 0)
                y: guide.snapToPixel(frame.y + (bottomEdge ? frame.height : 0))
                    - frame.y - (bottomEdge ? height : 0)
                width: guide.snapToPixel(Math.min(22, frame.width / 4, frame.height / 4))
                height: width

                Rectangle {
                    y: corner.bottomEdge ? corner.height - height : 0
                    width: corner.width
                    height: guide.strokeWidth
                    color: guide.markColor
                }

                Rectangle {
                    x: corner.rightEdge ? corner.width - width : 0
                    width: guide.strokeWidth
                    height: corner.height
                    color: guide.markColor
                }
            }
        }

        Rectangle {
            anchors.centerIn: parent
            anchors.alignWhenCentered: false
            width: 14
            height: width
            radius: width / 2
            color: "transparent"
            border.color: guide.markColor
            border.width: guide.strokeWidth
        }

        Rectangle {
            x: guide.snapToPixel((guide.width - width) / 2) - frame.x
            y: guide.snapToPixel((guide.height - height) / 2) - frame.y
            width: guide.snapToPixel(26)
            height: guide.strokeWidth
            color: guide.markColor
        }

        Rectangle {
            x: guide.snapToPixel((guide.width - width) / 2) - frame.x
            y: guide.snapToPixel((guide.height - height) / 2) - frame.y
            width: guide.strokeWidth
            height: guide.snapToPixel(26)
            color: guide.markColor
        }
    }
}
