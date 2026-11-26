# Viewport overlays

Place one QML component per file in this directory. KiPng loads these files in
filename order after the board is framed. Each component receives the viewport
as a `required property Item viewport`. Use an `Item` as the component root and
anchor its visible content within it. Handle input only where the feature needs
it so dragging and scrolling still reach the board elsewhere.

Read `viewport.cameraAngles` or `viewport.cameraDistance` to follow the camera.
Call `viewport.setCameraView(pitch, yaw, alignLongAxis)` to change the pose and
refit the board. The installer includes QML files in this directory.
