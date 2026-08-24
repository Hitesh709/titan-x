# TITAN X 3D Model Slots

The hero scene is genuinely WebGL/Three.js and currently uses optimized procedural PBR bull/bear geometry, so the site does not depend on a binary asset being available during deployment.

When production GLB assets are supplied, place them here as:

- `/models/titanx-bear.glb`
- `/models/titanx-bull.glb`

The reusable `TitanXBullBearScene` already exposes `bearModelUrl` and `bullModelUrl` props so the final assets can be wired without changing the hero API.

Recommended assets: GLB 2.0, PBR materials, under 8 MB each, origin centered, facing -Z, real-time friendly topology, 2K or compressed textures.
