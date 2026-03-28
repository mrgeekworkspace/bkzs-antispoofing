/**
 * GlobeController — 3D Earth with real-time satellite tracking
 * Shows satellite constellation, connection lines, receiver position from WebSocket data
 */
class GlobeController {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;

        // Orbital constants — must match backend simulator.py
        this.ORBIT_R = 2.55;
        this.EARTH_R = 1.5;
        this.PLANES = 6;
        this.PER_PLANE = 4;
        this.INCL = 55 * Math.PI / 180;

        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.earthGroup = null;
        this.satellites = [];
        this.connectionLines = [];
        this.satsByPrn = new Map();
        this.attackType = 'NOMINAL';
        this.receiverLat = 39.93;
        this.receiverLon = 32.87;
        this.stationPos3 = null;
        this.autoRotate = true;
        this.mouseDown = false;
        this.prevMouse = { x: 0, y: 0 };
        this.rotX = 0.35;
        this.rotY = -0.55;
        this.linkedCount = 0;
        this.trackedCount = 0;

        this.init();
        this.createOverlay();
        this.animate();
    }

    init() {
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x06080c);

        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 200);
        this.camera.position.set(0, 1.2, 5.2);
        this.camera.lookAt(0, 0, 0);

        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(w, h);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.container.appendChild(this.renderer.domElement);

        // Lighting
        this.scene.add(new THREE.AmbientLight(0x404050, 0.6));
        const sun = new THREE.DirectionalLight(0xfff5e0, 0.9);
        sun.position.set(4, 2, 5);
        this.scene.add(sun);

        this.createStarfield();
        this.createEarth();
        this.createSatellites();
        this.createGroundStation();
        this.createConnectionLines();

        // Mouse interaction
        const el = this.renderer.domElement;
        el.addEventListener('mousedown', (e) => {
            this.mouseDown = true;
            this.prevMouse = { x: e.clientX, y: e.clientY };
            this.autoRotate = false;
        });
        el.addEventListener('mousemove', (e) => {
            if (!this.mouseDown) return;
            this.rotY += (e.clientX - this.prevMouse.x) * 0.004;
            this.rotX += (e.clientY - this.prevMouse.y) * 0.004;
            this.rotX = Math.max(-1.2, Math.min(1.2, this.rotX));
            this.prevMouse = { x: e.clientX, y: e.clientY };
        });
        el.addEventListener('mouseup', () => this.mouseDown = false);
        el.addEventListener('mouseleave', () => this.mouseDown = false);

        // Scroll to zoom
        el.addEventListener('wheel', (e) => {
            e.preventDefault();
            const z = this.camera.position.z + e.deltaY * 0.005;
            this.camera.position.z = Math.max(3.5, Math.min(9, z));
        }, { passive: false });

        window.addEventListener('resize', () => this.onResize());
    }

    createStarfield() {
        const starCount = 2000;
        const positions = new Float32Array(starCount * 3);
        const colors = new Float32Array(starCount * 3);

        for (let i = 0; i < starCount; i++) {
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            const r = 35 + Math.random() * 45;
            positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
            positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
            positions[i * 3 + 2] = r * Math.cos(phi);

            // Per-star brightness variation
            const brightness = 0.45 + Math.random() * 0.55;
            colors[i * 3] = brightness;
            colors[i * 3 + 1] = brightness;
            colors[i * 3 + 2] = brightness + Math.random() * 0.05;
        }

        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const mat = new THREE.PointsMaterial({
            size: 0.4,
            sizeAttenuation: false,
            vertexColors: true,
            transparent: true,
            opacity: 0.85,
        });
        this.scene.add(new THREE.Points(geo, mat));
    }

    createEarth() {
        this.earthGroup = new THREE.Group();
        this.scene.add(this.earthGroup);

        // Main sphere
        const earthGeo = new THREE.SphereGeometry(this.EARTH_R, 80, 80);
        const earthMat = new THREE.MeshPhongMaterial({
            color: 0x0f1a2e,
            emissive: 0x060d18,
            emissiveIntensity: 0.4,
            shininess: 8,
        });
        this.earth = new THREE.Mesh(earthGeo, earthMat);
        this.earthGroup.add(this.earth);

        // Latitude/longitude grid
        const gridMat = new THREE.LineBasicMaterial({ color: 0x2a3a55, transparent: true, opacity: 0.2 });
        const R = this.EARTH_R + 0.005;
        for (let lat = -60; lat <= 60; lat += 30) {
            const pts = [];
            const r = R * Math.cos(lat * Math.PI / 180);
            const y = R * Math.sin(lat * Math.PI / 180);
            for (let lon = 0; lon <= 360; lon += 4) {
                const t = lon * Math.PI / 180;
                pts.push(new THREE.Vector3(r * Math.cos(t), y, r * Math.sin(t)));
            }
            this.earthGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
        }
        for (let lon = 0; lon < 360; lon += 30) {
            const pts = [];
            for (let lat = -90; lat <= 90; lat += 4) {
                const p = lat * Math.PI / 180;
                const t = lon * Math.PI / 180;
                pts.push(new THREE.Vector3(R * Math.cos(p) * Math.cos(t), R * Math.sin(p), R * Math.cos(p) * Math.sin(t)));
            }
            this.earthGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
        }

        // Atmosphere rim
        const atmoMat = new THREE.MeshBasicMaterial({ color: 0x4488cc, transparent: true, opacity: 0.04, side: THREE.BackSide });
        this.earthGroup.add(new THREE.Mesh(new THREE.SphereGeometry(this.EARTH_R + 0.06, 48, 48), atmoMat));
    }

    createSatellites() {
        let idx = 0;
        for (let p = 0; p < this.PLANES; p++) {
            const raan = (p / this.PLANES) * Math.PI * 2;

            // Orbit path — added to earthGroup
            const pts = [];
            for (let a = 0; a <= 360; a += 3) {
                const ang = a * Math.PI / 180;
                let x = this.ORBIT_R * Math.cos(ang);
                let y = this.ORBIT_R * Math.sin(ang) * Math.sin(this.INCL);
                let z = this.ORBIT_R * Math.sin(ang) * Math.cos(this.INCL);
                const rx = x * Math.cos(raan) - z * Math.sin(raan);
                const rz = x * Math.sin(raan) + z * Math.cos(raan);
                pts.push(new THREE.Vector3(rx, y, rz));
            }
            const orbitColor = p < 2 ? 0x2299bb : 0x1a2a44;
            const orbitMat = new THREE.LineBasicMaterial({ color: orbitColor, transparent: true, opacity: p < 2 ? 0.15 : 0.06 });
            this.earthGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), orbitMat));

            for (let s = 0; s < this.PER_PLANE; s++) {
                const isBkzs = (p < 2 && s < 3);
                // PRN generation matching backend simulator.py line 105
                const prn = isBkzs ? `BKZS-${String(p * 3 + s + 1).padStart(2, '0')}` : `GPS-${String(idx + 1).padStart(2, '0')}`;

                const phase0 = (s / this.PER_PLANE) * Math.PI * 2 + p * 0.53;
                const speed = 5.8e-5 + Math.random() * 1.4e-5;

                const size = isBkzs ? 0.04 : 0.022;
                const color = isBkzs ? 0x22aacc : 0x556688;
                const dot = new THREE.Mesh(
                    new THREE.SphereGeometry(size, 8, 8),
                    new THREE.MeshBasicMaterial({ color })
                );
                dot.userData = {
                    isBkzs, phase0, speed, raan, incl: this.INCL,
                    orbitR: this.ORBIT_R, origColor: color,
                    cn0: 42, prn, visible: true, elevation: 45
                };

                // Add to earthGroup so it rotates with earth
                this.earthGroup.add(dot);
                this.satellites.push(dot);

                const satIndex = this.satellites.length - 1;
                this.satsByPrn.set(prn, { dot, index: satIndex });

                idx++;
            }
        }
    }

    createGroundStation() {
        this.stationPos3 = this._latLonToVec3(this.receiverLat, this.receiverLon, this.EARTH_R + 0.02);

        // Solid marker
        this.stationDot = new THREE.Mesh(
            new THREE.SphereGeometry(0.035, 12, 12),
            new THREE.MeshBasicMaterial({ color: 0x22c55e })
        );
        this.stationDot.position.copy(this.stationPos3);
        this.earthGroup.add(this.stationDot);

        // Pulsing ring
        this.stationRing = new THREE.Mesh(
            new THREE.RingGeometry(0.05, 0.065, 24),
            new THREE.MeshBasicMaterial({ color: 0x22c55e, transparent: true, opacity: 0.35, side: THREE.DoubleSide })
        );
        this.stationRing.position.copy(this.stationPos3);
        this.stationRing.lookAt(0, 0, 0);
        this.earthGroup.add(this.stationRing);
    }

    createConnectionLines() {
        for (let i = 0; i < this.satellites.length; i++) {
            const positions = new Float32Array(6); // 2 vertices x 3 components
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

            const mat = new THREE.LineBasicMaterial({
                color: 0x22c55e,
                transparent: true,
                opacity: 0.20,
            });

            const line = new THREE.Line(geo, mat);
            line.visible = false;
            line.frustumCulled = false;
            this.earthGroup.add(line);
            this.connectionLines.push(line);
        }
    }

    createOverlay() {
        const ov = document.createElement('div');
        ov.id = 'globe-overlay';
        ov.style.cssText = 'position:absolute;bottom:10px;left:12px;pointer-events:none;z-index:10;';
        ov.innerHTML = `
            <div style="font-size:10px;color:#6b7280;line-height:1.7;font-family:Inter,sans-serif">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22aacc;margin-right:4px;vertical-align:middle"></span>BKZS &nbsp;
                <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#556688;margin-right:4px;vertical-align:middle"></span>GPS &nbsp;
                <span id="globe-station-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:4px;vertical-align:middle"></span>
                <span id="globe-rx-label">Ankara RX</span>
            </div>
            <div id="globe-status-line" style="font-size:11px;color:#9ca3af;margin-top:3px;font-family:'JetBrains Mono',monospace"></div>
        `;
        this.container.style.position = 'relative';
        this.container.appendChild(ov);
    }

    _latLonToVec3(lat, lon, r) {
        const phi = (90 - lat) * Math.PI / 180;
        const theta = (lon + 180) * Math.PI / 180;
        return new THREE.Vector3(
            -r * Math.sin(phi) * Math.cos(theta),
            r * Math.cos(phi),
            r * Math.sin(phi) * Math.sin(theta)
        );
    }

    update(data) {
        if (!data) return;
        this.attackType = data.detection?.type || 'NOMINAL';

        // Update receiver position
        if (data.receiver) {
            this.receiverLat = data.receiver.lat;
            this.receiverLon = data.receiver.lon;
            this.stationPos3 = this._latLonToVec3(this.receiverLat, this.receiverLon, this.EARTH_R + 0.02);
            if (this.stationDot) this.stationDot.position.copy(this.stationPos3);
            if (this.stationRing) {
                this.stationRing.position.copy(this.stationPos3);
                this.stationRing.lookAt(0, 0, 0);
            }
        }

        // Update satellites by PRN
        const sats = data.satellites || [];
        let tracked = 0;
        let linked = 0;

        sats.forEach((sd, i) => {
            const entry = this.satsByPrn.get(sd.prn);
            // Fall back to index if PRN not found (first frames before PRN sync)
            const dot = entry ? entry.dot : (i < this.satellites.length ? this.satellites[i] : null);
            const lineIdx = entry ? entry.index : i;
            if (!dot) return;

            dot.userData.cn0 = sd.cn0;
            dot.userData.prn = sd.prn;
            dot.userData.visible = sd.visible;
            dot.userData.elevation = sd.elevation;

            // Satellite color by CN0
            if (sd.cn0 < 20) dot.material.color.setHex(0xef4444);
            else if (sd.cn0 < 30) dot.material.color.setHex(0xf59e0b);
            else dot.material.color.setHex(dot.userData.origColor);

            if (sd.visible) tracked++;

            // Connection line visibility and color
            const line = lineIdx < this.connectionLines.length ? this.connectionLines[lineIdx] : null;
            if (line) {
                const showLine = sd.visible && sd.elevation > 5;
                line.visible = showLine;
                if (showLine) {
                    linked++;
                    // Color by attack state or CN0
                    if (this.attackType === 'SPOOFING') {
                        line.material.color.setHex(0xef4444);
                        line.material.opacity = 0.35;
                    } else if (this.attackType === 'JAMMING') {
                        line.material.color.setHex(0xf59e0b);
                        line.material.opacity = 0.30;
                    } else if (sd.cn0 >= 34) {
                        line.material.color.setHex(0x22c55e);
                        line.material.opacity = 0.20;
                    } else if (sd.cn0 >= 24) {
                        line.material.color.setHex(0xf59e0b);
                        line.material.opacity = 0.25;
                    } else {
                        line.material.color.setHex(0xef4444);
                        line.material.opacity = 0.30;
                    }
                }
            }
        });

        this.trackedCount = tracked;
        this.linkedCount = linked;

        // Station color by threat
        const stationColors = { NOMINAL: 0x22c55e, JAMMING: 0xf59e0b, SPOOFING: 0xef4444, ANOMALY: 0xf59e0b };
        const c = stationColors[this.attackType] || stationColors.NOMINAL;
        if (this.stationDot) this.stationDot.material.color.setHex(c);
        if (this.stationRing) this.stationRing.material.color.setHex(c);

        // Update overlay
        const stDot = document.getElementById('globe-station-dot');
        if (stDot) stDot.style.background = '#' + c.toString(16).padStart(6, '0');

        const rxLabel = document.getElementById('globe-rx-label');
        if (rxLabel) {
            rxLabel.textContent = this.attackType === 'NOMINAL' ? 'Ankara RX' : `Ankara RX \u2014 ${this.attackType}`;
            rxLabel.style.color = this.attackType === 'NOMINAL' ? '#9ca3af' : '#' + c.toString(16).padStart(6, '0');
        }

        const statusLine = document.getElementById('globe-status-line');
        if (statusLine && data.receiver) {
            statusLine.textContent = `${this.receiverLat.toFixed(4)}N ${this.receiverLon.toFixed(4)}E | ${tracked} tracked | ${linked} linked`;
        }
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        const t = Date.now();

        if (this.autoRotate) this.rotY += 0.0006;
        if (this.earthGroup) {
            this.earthGroup.rotation.y = this.rotY;
            this.earthGroup.rotation.x = this.rotX;
        }

        // Animate satellite positions (in earthGroup local space)
        this.satellites.forEach((dot, i) => {
            const d = dot.userData;
            const angle = d.phase0 + t * d.speed * 0.001;
            let x = d.orbitR * Math.cos(angle);
            let y = d.orbitR * Math.sin(angle) * Math.sin(d.incl);
            let z = d.orbitR * Math.sin(angle) * Math.cos(d.incl);
            const rx = x * Math.cos(d.raan) - z * Math.sin(d.raan);
            const rz = x * Math.sin(d.raan) + z * Math.cos(d.raan);
            dot.position.set(rx, y, rz);

            // Update connection line endpoints
            const line = this.connectionLines[i];
            if (line && line.visible && this.stationPos3) {
                const pos = line.geometry.attributes.position.array;
                // Vertex 0: ground station
                pos[0] = this.stationPos3.x;
                pos[1] = this.stationPos3.y;
                pos[2] = this.stationPos3.z;
                // Vertex 1: satellite
                pos[3] = rx;
                pos[4] = y;
                pos[5] = rz;
                line.geometry.attributes.position.needsUpdate = true;
            }
        });

        // Pulse station ring
        if (this.stationRing) {
            const speed = this.attackType !== 'NOMINAL' ? 0.006 : 0.002;
            this.stationRing.material.opacity = 0.15 + 0.2 * Math.abs(Math.sin(t * speed));
        }

        this.renderer.render(this.scene, this.camera);
    }

    onResize() {
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.globeController = new GlobeController('globe-container');
});
