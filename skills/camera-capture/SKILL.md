---
name: camera-capture
description: Capture images from device camera. Currently a placeholder - camera support depends on device capabilities.
version: "1.0.0"
tags:
  - camera
  - device
  - multimedia
triggers:
  - "take a photo"
  - "capture image"
  - "use camera"
  - "take picture"
entrypoints:
  capture:
    description: Capture an image from the default camera (not implemented)
  list:
    description: List available cameras (not implemented)
required_permissions:
  - camera
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: device-integration
  node_capability: camera
  status: stub
---

# Camera Capture Skill

> ⚠️ **Stub Skill**: This is a placeholder for future camera functionality.

## Current Status

Camera capture is **not available** on this device/node. This skill is a stub marking a future expansion point for the multi-node architecture.

## When Camera Will Be Supported

Camera functionality will be implemented when:
1. A companion node with camera capability is connected
2. The user explicitly grants camera permissions
3. The device has an accessible camera API

## Planned Features

### Capture Image
Capture a single image from the default camera.

```
Not implemented - returns "Camera not available on this device"
```

### List Cameras
List available camera devices.

```
Not implemented - returns "Camera not available on this device"
```

## Multi-Node Architecture

In the future, camera requests can be routed to a companion node (e.g., a phone or Raspberry Pi with camera) using the `node_capability: camera` metadata.

Example routing flow:
1. User says "take a photo"
2. Gateway checks for nodes with `camera` capability
3. If found, routes request to that node
4. Node captures image and returns it

## Notes

- Camera access requires user consent
- Images should be stored with proper privacy controls
- Consider thumbnail generation for previews
- Support for both front and back cameras (on mobile devices)

