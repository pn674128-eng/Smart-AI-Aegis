// 1. 括號平衡檢查
// 2. 邏輯驗算 (手算 D=10 S50C 5 工法)
import fs from 'fs';

// ─── 括號檢查 ───
const f = 'smart_ai_cam_mcp/regular_milling.py';
const t = fs.readFileSync(f, 'utf8');
let p=0, b=0, c=0, inStr=null, inComment=false;
for (let i = 0; i < t.length; i++) {
  const ch = t[i];
  if (ch === '\n') { inComment = false; continue; }
  if (inComment) continue;
  if (!inStr && (ch === '"' || ch === "'")) {
    const tri = t.substr(i, 3);
    if (tri === '"""' || tri === "'''") { inStr = tri; i += 2; continue; }
    inStr = ch; continue;
  }
  if (inStr) {
    if (inStr.length === 3) {
      if (t.substr(i, 3) === inStr) { inStr = null; i += 2; }
    } else {
      if (ch === '\\') { i++; continue; }
      if (ch === inStr) inStr = null;
    }
    continue;
  }
  if (ch === '#') { inComment = true; continue; }
  if (ch === '(') p++; else if (ch === ')') p--;
  else if (ch === '[') b++; else if (ch === ']') b--;
  else if (ch === '{') c++; else if (ch === '}') c--;
}
const lines = t.split('\n').length;
console.log(`Brackets: lines=${lines} ()=${p} []=${b} {}=${c} ${(p===0&&b===0&&c===0)?'OK':'BAD'}`);

// ─── 邏輯驗算 ───
const PI = Math.PI;
function engagement(D, AE) {
  if (AE >= D) return PI;
  if (AE <= 0) return 0;
  return Math.acos(1 - 2*AE/D);
}
function hex(D, AE, fz) {
  if (2*AE >= D) return fz;
  return fz * Math.sin(engagement(D, AE));
}

console.log('\n=== S50C D=10 5 工法手算驗證 (ER20 切削油) ===');
const cases = [
  // name, vc, fz_func, ae, ap_func, expected_rpm, expected_F
  ['面銑',   100, D => D*0.01,           7.5,   0.6,    3185, 1274],
  ['側銑',   100, D => D*0.01,           0.3,   20.0,   3185, 1274],  // 未補償
  ['滿刃銑',  70, D => D*0.01/2.5,       10.0,  5.0,    2229,  357],
  ['插銑',   80,  D => 0.025,            0.5,   27.0,   2546,  254],
];
for (const [name, vc, fzFn, ae, ap, expR, expF] of cases) {
  const D = 10, Z = 4;
  const fz = fzFn(D);
  const rpm = vc * 1000 / (PI * D);
  const F = fz * Z * rpm;
  const theta = engagement(D, ae);
  const h = hex(D, ae, fz);
  const mrr = ae * ap * F;
  console.log(`  ${name}: Vc=${vc} fz=${fz.toFixed(4)} → RPM=${rpm.toFixed(0)}(exp ${expR}) F=${F.toFixed(0)}(exp ${expF}) θ=${(theta*180/PI).toFixed(1)}° hex=${h.toFixed(4)} MRR=${mrr.toFixed(0)}`);
}

// ─── 側銑 Chip Thinning 補償驗算 (70% 切削油) ───
console.log('\n=== 側銑 Chip Thinning 補償 (S50C, D=10, AE=0.3, 切削油 70%) ===');
const D = 10, AE = 0.3, Z = 4;
const fz_base = D * 0.01; // 0.1
const hex_target = 0.030;
const theta = engagement(D, AE);
const sinT = Math.sin(theta);
const fz_full = hex_target / sinT;
const fz_70 = fz_base + (fz_full - fz_base) * 0.70;
const rpm = 100 * 1000 / (PI * D);
console.log(`  θ=${(theta*180/PI).toFixed(2)}° sin=${sinT.toFixed(4)}`);
console.log(`  fz_baseline (= D×0.01) = ${fz_base}`);
console.log(`  fz_full_compensate (hex=0.03) = ${fz_full.toFixed(4)}`);
console.log(`  fz_70%_compensate (切削油) = ${fz_70.toFixed(4)}`);
console.log(`  → F at fz_70 = ${(fz_70*Z*rpm).toFixed(0)} mm/min`);
console.log(`  → hex actual at fz_70 = ${(fz_70*sinT).toFixed(4)}`);

// ─── 孔銑 階梯驗算 ===
console.log('\n=== 孔銑 階梯 (D=10 銑刀 銑不同孔徑 S50C) ===');
const F_face = 1274;
const F_base_hole = F_face / 2;
const tests = [
  [10.5, '<0.5'],
  [11.0, '0.5~1'],
  [12.0, '>1'],
  [15.0, '>1 (大空間)'],
];
for (const [hole_d, band] of tests) {
  const u_ae = (hole_d - 10) / 2;
  let mod = 1.0, reason = '';
  if (u_ae < 0.5) { mod = 0.5; reason = '空間有限'; }
  else if (u_ae < 1.0) { mod = 0.75; reason = '空間受限'; }
  else { mod = 1.0; reason = '空間良好'; }
  const F = F_base_hole * mod;
  const F_capped = Math.min(F, F_face);
  console.log(`  孔徑 ${hole_d} → 單邊AE=${u_ae.toFixed(2)} (${band}) → F=${F_base_hole}×${mod}=${F.toFixed(0)} (cap=${F_capped}) [${reason}]`);
}

// ─── 推到其他材質 (Vc 縮放) ===
console.log('\n=== Vc 縮放推到其他材質 (D=10 面銑) ===');
const scales = [
  ['AL6061', 2.00], ['Brass', 2.50], ['NAK80', 0.75],
  ['SUS304', 0.70], ['Ti-6Al-4V', 0.60], ['Inconel', 0.40],
];
for (const [mat, scale] of scales) {
  const vc = 100 * scale;
  const rpm = vc * 1000 / (PI * 10);
  const F = 0.1 * 4 * rpm;
  console.log(`  ${mat}: Vc=${vc} RPM=${rpm.toFixed(0)} F=${F.toFixed(0)}`);
}
