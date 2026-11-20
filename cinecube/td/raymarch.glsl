// cinecube ray marcher, touchdesigner glsl top. input 0 = the cube as a 3d texture (r = T in K, clipped >= 0)
// voxel x y z = ra px, dec px, channel. world = voxel units, z scaled by uStretch. ortho camera, 1 px per voxel.
// plain pass (theta 0, stretch 1, step 1, nearest, everything else off) = sum over channels of T * dv = the clipped
// moment0, exactly (the gate checks this).
// output r = radiance in K km/s, g = transmittance, b = depth of the emission centroid (world z), a = 1

uniform vec4 uDim;    // nx ny nz, sigma K (for the transfer functions)
uniform vec4 uCam;    // theta_deg, stretch, step (world units), interp (0 nearest, 1 trilinear)
uniform vec4 uPhys;   // dv km/s, kappa (absorption per K km/s), emission scale, composite (0 additive, 1 max)
uniform vec4 uTf;     // transfer (0 linear 1 log 2 asinh 3 threshold), threshold k, dof sigma px, dof samples
uniform vec4 uLight;  // strength (0 = unlit), shadow kappa (per K km/s), shadow step, unused

out vec4 fragColor;

float voxel(ivec3 i) {
    if (any(lessThan(i, ivec3(0))) || any(greaterThanEqual(i, ivec3(uDim.xyz)))) return 0.0;
    return texelFetch(sTD3DInputs[0], i, 0).r;
}

float sampleT(vec3 p) {  // p in voxel units, voxel k covers [k, k+1)
    if (uCam.w < 0.5) return voxel(ivec3(floor(p)));
    vec3 q = p - 0.5;
    ivec3 b = ivec3(floor(q));
    vec3 f = q - vec3(b);
    float c000 = voxel(b), c100 = voxel(b + ivec3(1,0,0)), c010 = voxel(b + ivec3(0,1,0)), c110 = voxel(b + ivec3(1,1,0));
    float c001 = voxel(b + ivec3(0,0,1)), c101 = voxel(b + ivec3(1,0,1)), c011 = voxel(b + ivec3(0,1,1)), c111 = voxel(b + ivec3(1,1,1));
    return mix(mix(mix(c000, c100, f.x), mix(c010, c110, f.x), f.y), mix(mix(c001, c101, f.x), mix(c011, c111, f.x), f.y), f.z);
}

float tf(float T) {
    int m = int(uTf.x + 0.5);
    if (m == 1) return log(1.0 + max(T, 0.0) / uDim.w) / log(10.0);
    if (m == 2) { float x = max(T, 0.0) / uDim.w; return log(x + sqrt(x * x + 1.0)); }
    if (m == 3) return T > uTf.y * uDim.w ? T : 0.0;
    return T;
}

vec2 slab(vec3 P, vec3 d, vec3 box) {
    vec3 inv = 1.0 / (d + vec3(1e-12));
    vec3 t0 = -P * inv, t1 = (box - P) * inv;
    return vec2(max(max(min(t0.x, t1.x), min(t0.y, t1.y)), min(t0.z, t1.z)),
                min(min(max(t0.x, t1.x), max(t0.y, t1.y)), max(t0.z, t1.z)));
}

float shadow(vec3 p, vec3 box, float s) {   // transmittance from p toward the light
    if (uLight.x <= 0.0) return 1.0;
    vec3 Ld = normalize(vec3(0.0, 0.6, 0.8));  // light up and toward the camera, same direction as track a's shading
    vec2 tt = slab(p, Ld, box);
    float dl = uLight.z, od = 0.0;
    int n = int(ceil(max(tt.y, 0.0) / dl));
    for (int i = 0; i < 1024; i++) {
        if (i >= n) break;
        vec3 q = p + (float(i) + 0.5) * dl * Ld;
        od += uLight.y * tf(sampleT(vec3(q.xy, q.z / s))) * dl / s * uPhys.x;
    }
    return exp(-od);
}

void main() {
    float th = radians(uCam.x), s = uCam.y, ds = uCam.z;
    vec3 box = vec3(uDim.xy, uDim.z * s);
    vec3 C = 0.5 * box;
    vec3 dir = vec3(-sin(th), 0.0, -cos(th));
    vec3 right = vec3(cos(th), 0.0, -sin(th));
    vec3 up = vec3(0.0, 1.0, 0.0);
    vec2 px = gl_FragCoord.xy;                       // pixel centers at k + 0.5
    vec3 P = C + (px.x - 0.5 * uDim.x) * right + (px.y - 0.5 * uDim.y) * up;
    vec2 tt = slab(P, dir, box);
    float tc = dot(C - P, dir), h = 0.5 * box.z;     // depth of the focus plane (volume center), half depth
    int nap = uTf.z > 0.0 ? max(int(uTf.w), 1) : 1;
    float w = ds / s * uPhys.x;                      // each step carries ds / stretch channels of dv
    float Lsum = 0.0, Trsum = 0.0, zsum = 0.0;
    if (tt.y > tt.x) {
        int n = int(ceil((tt.y - tt.x) / ds));
        for (int k = 0; k < 256; k++) {
            if (k >= nap) break;
            // thin lens on an ortho camera: gaussian aperture offsets (std = dof sigma px at the front / back face),
            // the ray is sheared so blur grows with |depth - focus|, like track a's dof
            vec2 a = vec2(0.0);
            if (nap > 1) {
                float u = (float(k) + 0.5) / float(nap);
                float r = uTf.z * sqrt(-2.0 * log(1.0 - u));
                float ang = float(k) * 2.39996323;
                a = r * vec2(cos(ang), sin(ang));
            }
            float L = 0.0, Tr = 1.0, zs = 0.0;
            for (int i = 0; i < 4096; i++) {
                if (i >= n) break;
                float t = tt.x + (float(i) + 0.5) * ds;
                vec3 p = P + t * dir + (a.x * right + a.y * up) * ((t - tc) / h);
                float E = tf(sampleT(vec3(p.xy, p.z / s)));
                if (uPhys.w > 0.5) { L = max(L, E); continue; }
                float lit = uLight.x > 0.0 ? (1.0 - uLight.x) + uLight.x * shadow(p, box, s) : 1.0;
                float e = uPhys.z * E * w * lit;
                L += Tr * e;
                zs += Tr * e * p.z;
                Tr *= exp(-uPhys.y * E * w);
            }
            Lsum += L; Trsum += Tr; zsum += zs;
        }
    }
    float inv = 1.0 / float(nap);
    fragColor = TDOutputSwizzle(vec4(Lsum * inv, Trsum * inv, Lsum > 0.0 ? zsum / Lsum : 0.0, 1.0));
}
