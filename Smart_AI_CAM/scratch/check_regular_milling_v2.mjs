// 驗證修正後的 chip_thinning 邏輯
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
console.log(`Brackets: ()=${p} []=${b} {}=${c} ${(p===0&&b===0&&c===0)?'OK':'BAD'}`);
console.log(`Lines: ${t.split('\n').length}`);

const PI = Math.PI;
const D = 10, Z = 4;

function engagement(D, AE) { if(AE>=D)return PI; if(AE<=0)return 0; return Math.acos(1-2*AE/D); }
function hex_fn(D, AE, fz) { if(2*AE>=D)return fz; return fz * Math.sin(engagement(D, AE)); }

// 側銑修正後行為驗算
console.log('\n=== 側銑 chip_thinning_compensation 三檔對比 (D=10, AE=0.3, S50C) ===');
const AE = 0.3;
const sinT = Math.sin(engagement(D, AE));
const fz_base = D * 0.01; // 0.1 (用戶實機)
const hex_target_air = 0.050; // 動態極限
const fz_full = hex_target_air / sinT;
const rpm = 100 * 1000 / (PI * D);

for (const comp of [0.0, 0.5, 1.0]) {
  let fz_program = fz_base;
  let applied = false;
  if (comp > 0 && fz_full > fz_base) {
    fz_program = fz_base + (fz_full - fz_base) * comp;
    applied = true;
  }
  const F = fz_program * Z * rpm;
  const hex_actual = fz_program * sinT;
  console.log(`  comp=${comp.toFixed(1)} → fz=${fz_program.toFixed(4)} F=${F.toFixed(0)} hex=${hex_actual.toFixed(4)} applied=${applied}`);
}
console.log('  → 預設 comp=0 給用戶實機 (F=1273), 升級到 comp=1 給動態極限 (F=1871)');

// 健康度檢查
console.log('\n=== hex 健康度檢查 (5 工法 S50C D=10) ===');
const cases = [
  ['面銑',   0.1,     7.5,  '無減薄'],
  ['側銑',   0.1,     0.3,  '減薄, 但 OK'],
  ['滿刃銑', 0.04,    10,   '滿刀, 無減薄'],
  ['插銑',   0.025,   0.5,  '減薄大'],
];
for (const [name, fz, ae, note] of cases) {
  const h = hex_fn(D, ae, fz);
  let status = 'OK';
  if (h < 0.015) status = 'RUBBING_RISK';
  else if (h > 0.080) status = 'OVERLOAD_RISK';
  console.log(`  ${name}: fz=${fz} AE=${ae} → hex=${h.toFixed(4)} [${status}] (${note})`);
}

// 微徑 + 動態 = 容易 RUBBING_RISK
console.log('\n=== 微徑警告測試 (D=2 側銑 AE=0.05D=0.1) ===');
const D2 = 2;
const AE2 = 0.1;
const fz2 = D2 * 0.01; // 0.02
const sinT2 = Math.sin(engagement(D2, AE2));
const hex2 = fz2 * sinT2;
console.log(`  D=2 AE=0.1 fz=${fz2} → hex=${hex2.toFixed(4)} ${hex2 < 0.015 ? '⚠ RUBBING_RISK 預期觸發' : 'OK'}`);
