/* Hero character — WebGL upgrade.
 *
 * The hero already works without this file: motion.js tilts the flat cutout
 * (.hero_char) toward the cursor, which is what ships if anything here bails.
 * This module replaces that cutout with the real mesh once it has loaded, so
 * the character turns with actual parallax instead of a skewed image.
 *
 * It is strictly an upgrade path. Every failure — no WebGL, slow link, decode
 * error, reduced-motion, touch — leaves the cutout in place and returns. The
 * canvas only becomes visible after the model is on screen, so there is no
 * flash of empty space and no layout shift either way.
 *
 * The mesh comes from single-image reconstruction, so it is accurate from the
 * front and invented behind. Yaw is capped at 20 degrees for that reason: past
 * roughly 45 the head reads as a flat slab. That cap is a quality limit, not a
 * stylistic one — raising it will show the reconstruction's weak side.
 */
import * as THREE from "/assets/vendor/three.module.min.js";
import { GLTFLoader } from "/assets/vendor/GLTFLoader.js";

const MODEL = "/assets/character/character.glb";
const MAX_YAW = 20 * Math.PI / 180;
const MAX_PITCH = 7 * Math.PI / 180;
const EASE = 0.055;                 // per-frame approach to the cursor target

const host = document.querySelector("[data-hero-image], .hero_image");
const flat = document.querySelector("[data-hero-char]");

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const fine = matchMedia("(pointer: fine)").matches;
const wide = matchMedia("(min-width: 992px)").matches;
/* Respect an explicit data-saver request before spending a megabyte on it. */
const thrifty = navigator.connection && navigator.connection.saveData;

if (host && flat && !reduced && fine && wide && !thrifty) start();

function start() {
  let gl;
  try {
    gl = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  } catch (err) {
    return;                          // no WebGL: the cutout stays
  }

  const canvas = gl.domElement;
  canvas.className = "hero_char_gl";
  canvas.setAttribute("aria-hidden", "true");
  gl.setPixelRatio(Math.min(devicePixelRatio, 2));
  gl.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);

  /* Lit to match the section it stands in: a warm key from the front left, a
     red bounce from below (the ground he is standing on), and a cool rim to
     lift his silhouette off a background of nearly the same hue. */
  scene.add(new THREE.HemisphereLight(0xffd9c9, 0x3a0d0b, 1.5));
  const key = new THREE.DirectionalLight(0xfff0e2, 2.6);
  key.position.set(-2.4, 3.4, 4.2);
  scene.add(key);
  const bounce = new THREE.DirectionalLight(0xff5a34, 1.1);
  bounce.position.set(1.5, -2.2, 1.8);
  scene.add(bounce);
  const rim = new THREE.DirectionalLight(0xffb59c, 1.6);
  rim.position.set(3.0, 1.6, -3.4);
  scene.add(rim);

  const pivot = new THREE.Group();
  scene.add(pivot);

  let model = null;
  let raf = 0, visible = false;
  const target = { yaw: 0, pitch: 0 };
  const now = { yaw: 0, pitch: 0 };

  /* A sample of the mesh's vertices in unit space, kept for the framing
     calibration below — projecting a few thousand points is cheap and exact,
     where the bounding box alone is not (perspective makes his nose and the
     camera in his hand project larger than the box's own corners). */
  let sample = null, baseScale = 1;

  new GLTFLoader().load(MODEL, (gltf) => {
    model = gltf.scene;

    /* Recentre and scale to unit height so framing does not depend on the
       exporter's units. These are two nested objects on purpose: three.js
       composes as T * R * S, so a position set on the same object as the scale
       would not itself be scaled, and the model would sit off its own centre. */
    const box = new THREE.Box3().setFromObject(model);
    const size = new THREE.Vector3(), mid = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(mid);
    model.position.sub(mid);
    /* The reconstruction already faces +Z, which is where three.js puts the
       camera — no turn needed. (Rotating by PI here faces him away; the
       offline check renders that suggested otherwise use a +Z-looking camera,
       the opposite of three.js's convention.) */

    const unit = new THREE.Group();
    baseScale = 1 / size.y;
    unit.scale.setScalar(baseScale);
    unit.add(model);
    pivot.add(unit);

    /* Sampled in `unit`'s own space, because fit() re-applies unit.matrix and
       pivot.matrix when it projects — sampling in world space would apply
       both twice. */
    pivot.updateMatrixWorld(true);
    const toUnit = new THREE.Matrix4().copy(unit.matrixWorld).invert();
    sample = [];
    const v = new THREE.Vector3();
    model.traverse((o) => {
      if (!o.isMesh) return;
      const pos = o.geometry.attributes.position;
      const step = Math.max(1, Math.floor(pos.count / 3000));
      for (let i = 0; i < pos.count; i += step) {
        v.set(pos.getX(i), pos.getY(i), pos.getZ(i))
          .applyMatrix4(o.matrixWorld).applyMatrix4(toUnit);
        sample.push(v.clone());
      }
    });

    fit();
    /* Render one frame before the canvas is ever shown, so the cross-fade
       reveals the character rather than an empty buffer. */
    gl.render(scene, camera);
    host.appendChild(canvas);
    /* Cross-fade rather than swap, so the upgrade is never a visible pop. The
       reflow read commits opacity:0 as the transition's start value. A rAF
       would be the usual idiom, but it never fires in a background tab, which
       would leave the canvas permanently invisible. */
    void canvas.offsetWidth;
    canvas.classList.add("is-in");
    flat.classList.add("is-out");
    /* motion.js is still tilting the cutout toward the cursor. It is invisible
       from here on, so stop paying for it — the mesh does that job now. */
    if (window.gsap) window.gsap.killTweensOf(flat);
    tick();
  }, undefined, () => { /* decode or network failure: cutout stays */ });

  /* Frame him exactly where the cutout he replaces sits: 60% of the section's
     height (52% under 992px), standing on the baseline, horizontally centred.
     Solved by measurement rather than formula — under perspective the parts of
     him nearest the camera project larger than his bounding box, so the closed
     form overshoots. Three passes converge to well under a pixel. */
  function fit() {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h || !sample) return;
    gl.setSize(w, h, false);
    camera.aspect = w / h;
    camera.position.set(0, 0, 2.4);
    camera.updateProjectionMatrix();
    /* project() reads camera.matrixWorldInverse, which the renderer refreshes
       — but fit() runs before the first render, and a stale identity there
       puts the camera inside the model and divides by zero. */
    camera.updateMatrixWorld(true);

    const share = matchMedia("(min-width: 992px)").matches ? 0.60 : 0.52;
    const unit = pivot.children[0];
    const v = new THREE.Vector3();
    /* Start from a known state — fit() also runs on resize, and corrections
       applied on top of previous corrections would drift. */
    unit.scale.setScalar(baseScale);
    pivot.position.set(0, 0, 0);

    const tan = Math.tan((camera.fov * Math.PI / 180) / 2);
    const Z = camera.position.z;

    for (let pass = 0; pass < 4; pass++) {
      pivot.rotation.set(0, 0, 0);
      pivot.updateMatrixWorld(true);
      let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
      for (const p of sample) {
        v.copy(p).applyMatrix4(unit.matrix).applyMatrix4(pivot.matrix).project(camera);
        const sx = (v.x * 0.5 + 0.5) * w, sy = (-v.y * 0.5 + 0.5) * h;
        if (sy < top) top = sy;
        if (sy > bottom) bottom = sy;
        if (sx < left) left = sx;
        if (sx > right) right = sx;
      }
      /* Scale to the target share, then drop his feet onto the baseline and
         centre his silhouette — not his origin, which the camera in his hand
         pulls off centre. A world unit at the model's depth is h/(2*tan*Z)
         screen pixels vertically, and w/(2*tan*aspect*Z) horizontally. */
      unit.scale.multiplyScalar((share * h) / (bottom - top));
      pivot.position.y -= (h - bottom) * 2 * tan * Z / h;
      pivot.position.x += (w / 2 - (left + right) / 2) * 2 * tan * camera.aspect * Z / w;
      pivot.updateMatrixWorld(true);
    }
  }

  addEventListener("resize", fit, { passive: true });

  addEventListener("pointermove", (ev) => {
    const nx = (ev.clientX / innerWidth) * 2 - 1;
    const ny = (ev.clientY / innerHeight) * 2 - 1;
    target.yaw = nx * MAX_YAW;
    target.pitch = ny * MAX_PITCH;
  }, { passive: true });

  document.addEventListener("mouseleave", () => { target.yaw = 0; target.pitch = 0; });

  /* Only render while the hero is actually on screen. */
  new IntersectionObserver((entries) => {
    visible = entries[0].isIntersecting;
    if (visible && !raf) tick();
  }).observe(host);

  function tick() {
    raf = visible ? requestAnimationFrame(tick) : 0;
    if (!model) return;
    now.yaw += (target.yaw - now.yaw) * EASE;
    now.pitch += (target.pitch - now.pitch) * EASE;
    pivot.rotation.y = now.yaw;
    pivot.rotation.x = now.pitch;
    /* A slow breath so he is alive when the cursor is still. */
    pivot.position.z = Math.sin(performance.now() / 2400) * 0.012;
    gl.render(scene, camera);
  }

  /* Expose for verification only — the page never calls this. */
  window.__hero3d = { get ready() { return !!model; }, gl, scene, camera, pivot, target, now };
}
