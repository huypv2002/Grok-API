const ADMIN_KEY = "huyem";

function cors(h = {}) {
  return { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS", "Access-Control-Allow-Headers": "Content-Type,X-Admin-Key", ...h };
}
function json(data, status = 200) { return Response.json(data, { status, headers: cors() }); }

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (request.method === "OPTIONS") return new Response(null, { headers: cors() });

    // POST /login
    if (path === "/login" && request.method === "POST") {
      const { username, password, machine_id } = await request.json();
      if (!username || !password) return json({ ok: false, error: "Missing credentials" }, 400);
      const row = await env.DB.prepare("SELECT username,password,plan,expires_at,is_active,machine_id FROM app_users WHERE username=?").bind(username).first();
      if (!row || row.password !== password) return json({ ok: false, error: "Sai tài khoản hoặc mật khẩu" }, 401);
      if (!row.is_active) return json({ ok: false, error: "Tài khoản đã bị khóa" }, 403);
      // Machine lock
      if (machine_id && row.machine_id && row.machine_id !== machine_id) {
        return json({ ok: false, error: "Tài khoản đã được đăng ký trên máy khác. Liên hệ admin để reset." }, 403);
      }
      // Auto-bind machine_id lần đầu login
      if (machine_id && !row.machine_id) {
        await env.DB.prepare("UPDATE app_users SET machine_id=? WHERE username=?").bind(machine_id, username).run();
      }
      return json({ ok: true, username: row.username, plan: row.plan, expires_at: row.expires_at });
    }

    // POST /check
    if (path === "/check" && request.method === "POST") {
      const { username, machine_id } = await request.json();
      if (!username) return json({ ok: false, error: "Missing username" }, 400);
      const row = await env.DB.prepare("SELECT username,plan,expires_at,is_active,machine_id FROM app_users WHERE username=?").bind(username).first();
      if (!row) return json({ ok: false, error: "User not found" }, 404);
      if (!row.is_active) return json({ ok: false, expired: true, error: "Tài khoản đã bị khóa" });
      // Machine check
      if (machine_id && row.machine_id && row.machine_id !== machine_id) {
        return json({ ok: false, expired: true, error: "Tài khoản đang dùng trên máy khác" });
      }
      const now = new Date().toISOString().split("T")[0];
      const expired = row.expires_at && row.expires_at < now;
      return json({ ok: !expired, expired: !!expired, plan: row.plan, expires_at: row.expires_at });
    }

    // Admin panel HTML
    if (path === "/admin") {
      return new Response(ADMIN_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }

    // ADMIN APIs
    if (path === "/admin/users") {
      if (request.headers.get("X-Admin-Key") !== ADMIN_KEY) return json({ error: "Unauthorized" }, 401);

      if (request.method === "GET") {
        const { results } = await env.DB.prepare("SELECT username,plan,expires_at,is_active,machine_id,created_at FROM app_users ORDER BY created_at DESC").all();
        return json({ users: results });
      }
      if (request.method === "POST") {
        const { username, password, plan, expires_at, machine_id } = await request.json();
        if (!username || !password) return json({ error: "Missing fields" }, 400);
        await env.DB.prepare(
          "INSERT OR REPLACE INTO app_users (username,password,plan,expires_at,is_active,machine_id) VALUES(?,?,?,?,1,?)"
        ).bind(username, password, plan || "trial", expires_at || "", machine_id || null).run();
        return json({ ok: true });
      }
      if (request.method === "PUT") {
        const { username, password, plan, expires_at, is_active, machine_id, reset_machine } = await request.json();
        if (!username) return json({ error: "Missing username" }, 400);
        const parts = [], vals = [];
        if (password !== undefined) { parts.push("password=?"); vals.push(password); }
        if (plan !== undefined) { parts.push("plan=?"); vals.push(plan); }
        if (expires_at !== undefined) { parts.push("expires_at=?"); vals.push(expires_at); }
        if (is_active !== undefined) { parts.push("is_active=?"); vals.push(is_active ? 1 : 0); }
        if (machine_id !== undefined) { parts.push("machine_id=?"); vals.push(machine_id); }
        if (reset_machine) { parts.push("machine_id=NULL"); }
        if (!parts.length) return json({ error: "Nothing to update" }, 400);
        vals.push(username);
        await env.DB.prepare("UPDATE app_users SET " + parts.join(",") + " WHERE username=?").bind(...vals).run();
        return json({ ok: true });
      }
      if (request.method === "DELETE") {
        const username = url.searchParams.get("username");
        if (!username) return json({ error: "Missing username" }, 400);
        await env.DB.prepare("DELETE FROM app_users WHERE username=?").bind(username).run();
        return json({ ok: true });
      }
    }

    return json({ error: "Not found" }, 404);
  },
};


const ADMIN_HTML = `<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grok Admin</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:linear-gradient(135deg,#0a0e1a,#121830);color:#fff;min-height:100vh;padding:20px}
h1{text-align:center;margin:15px 0 20px;font-size:22px}
.c{background:rgba(20,30,50,.85);border:1px solid rgba(80,120,200,.3);border-radius:12px;padding:20px;margin:12px auto;max-width:1100px}
.c h2{margin-bottom:12px;font-size:15px;color:rgba(255,255,255,.85)}
table{width:100%;border-collapse:collapse}
th,td{padding:9px 10px;text-align:left;border-bottom:1px solid rgba(80,120,200,.12);font-size:12px}
th{background:rgba(30,40,65,.9);color:rgba(255,255,255,.7);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.b{display:inline-block;padding:3px 10px;border-radius:10px;font-size:10px;font-weight:700}
.b.ok{background:#27ae60}.b.no{background:#e74c3c}.b.ex{background:#f39c12}
.mid{font-size:10px;color:rgba(255,255,255,.4);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
.mid:hover{color:#fff}
input,select{background:rgba(25,35,55,.95);color:#fff;border:1px solid rgba(80,120,200,.4);border-radius:6px;padding:7px 10px;font-size:12px;width:100%}
input:focus,select:focus{outline:none;border-color:rgba(80,120,200,.8)}
.fr{display:flex;gap:8px;margin-bottom:8px;align-items:end;flex-wrap:wrap}
.fr>div{flex:1;min-width:100px}
.fr label{display:block;font-size:10px;color:rgba(255,255,255,.5);margin-bottom:3px}
button{background:linear-gradient(90deg,#3498db,#2980b9);color:#fff;border:none;border-radius:6px;padding:7px 14px;cursor:pointer;font-size:12px;white-space:nowrap}
button:hover{opacity:.85}
.dl{background:linear-gradient(90deg,#e74c3c,#c0392b)}
.ed{background:linear-gradient(90deg,#f39c12,#e67e22)}
.tg{background:linear-gradient(90deg,#8e44ad,#9b59b6)}
.rs{background:linear-gradient(90deg,#16a085,#1abc9c)}
.ki{max-width:1100px;margin:8px auto;display:flex;gap:8px;align-items:center}
.ki input{max-width:250px}
.ki label{font-size:11px;color:rgba(255,255,255,.4)}
#m{text-align:center;padding:8px;font-size:12px;color:#2ecc71;min-height:20px}
</style></head><body>
<h1>🎬 Grok Admin Panel</h1>
<div class="ki"><label>Admin Key:</label><input type="password" id="ak" placeholder="Nhập admin key..."><button onclick="L()">🔄 Load</button></div>
<div id="m"></div>
<div class="c"><h2>➕ Thêm / Sửa tài khoản</h2>
<div class="fr">
<div><label>Username</label><input id="fu" placeholder="username"></div>
<div><label>Password</label><input id="fp" placeholder="password"></div>
<div><label>Gói</label><select id="fg"><option>trial</option><option>basic</option><option>premium</option></select></div>
<div><label>Hết hạn</label><input id="fe" type="date"></div>
<div><label>Machine ID</label><input id="fm" placeholder="Mã máy (user cung cấp)"></div>
<div><label>&nbsp;</label><button onclick="S()">💾 Lưu</button></div>
</div></div>
<div class="c"><h2>👤 Danh sách tài khoản</h2>
<table><thead><tr><th>Username</th><th>Gói</th><th>Hết hạn</th><th>Trạng thái</th><th>Machine ID</th><th>Ngày tạo</th><th>Thao tác</th></tr></thead>
<tbody id="ul"></tbody></table></div>
<script>
const A=location.origin,K=()=>document.getElementById('ak').value;
function M(t,c){const m=document.getElementById('m');m.textContent=t;m.style.color=c||'#2ecc71';setTimeout(()=>m.textContent='',3000)}
async function L(){
  const r=await fetch(A+'/admin/users',{headers:{'X-Admin-Key':K()}});
  if(!r.ok){M('Sai admin key','#e74c3c');return}
  const d=await r.json(),now=new Date().toISOString().split('T')[0];
  let h='';
  d.users.forEach(u=>{
    const exp=u.expires_at&&u.expires_at<now;
    const st=!u.is_active?'no':exp?'ex':'ok';
    const sl=st==='ok'?'Hoạt động':st==='ex'?'Hết hạn':'Khóa';
    const mid=u.machine_id||'';
    const midShort=mid?mid.slice(0,16)+'…':'chưa gán';
    h+=\`<tr><td>\${u.username}</td><td>\${u.plan||'trial'}</td><td>\${u.expires_at||'∞'}</td>
    <td><span class="b \${st}">\${sl}</span></td>
    <td class="mid" title="\${mid}" onclick="navigator.clipboard.writeText('\${mid}');M('Đã copy machine ID')">\${midShort}</td>
    <td>\${(u.created_at||'').slice(0,10)}</td>
    <td style="white-space:nowrap"><button class="ed" onclick="E('\${u.username}','\${mid}')">✏️</button>
    <button class="dl" onclick="D('\${u.username}')">🗑️</button>
    <button class="tg" onclick="T('\${u.username}',\${u.is_active?0:1})">\${u.is_active?'🔒':'🔓'}</button>
    \${mid?\`<button class="rs" onclick="R('\${u.username}')">🔄 Reset</button>\`:''}</td></tr>\`;
  });
  document.getElementById('ul').innerHTML=h||'<tr><td colspan="7">Trống</td></tr>';
}
async function S(){
  const u=document.getElementById('fu').value.trim(),p=document.getElementById('fp').value.trim(),m=document.getElementById('fm').value.trim();
  if(!u){M('Nhập username','#e74c3c');return}
  const b={username:u,plan:document.getElementById('fg').value,expires_at:document.getElementById('fe').value};
  if(p)b.password=p;
  if(m)b.machine_id=m;
  // Nếu có password → POST (tạo mới), không → PUT (sửa)
  if(p){
    const r=await fetch(A+'/admin/users',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify(b)});
    r.ok?M('Đã tạo!'):M('Lỗi','#e74c3c');
  } else {
    const r=await fetch(A+'/admin/users',{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify(b)});
    r.ok?M('Đã cập nhật!'):M('Lỗi','#e74c3c');
  }
  L();document.getElementById('fu').value='';document.getElementById('fp').value='';document.getElementById('fm').value='';
}
function E(u,mid){document.getElementById('fu').value=u;document.getElementById('fm').value=mid||'';document.getElementById('fp').focus()}
async function D(u){if(!confirm('Xóa '+u+'?'))return;await fetch(A+'/admin/users?username='+u,{method:'DELETE',headers:{'X-Admin-Key':K()}});M('Đã xóa');L()}
async function T(u,a){await fetch(A+'/admin/users',{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify({username:u,is_active:!!a})});M(a?'Đã mở':'Đã khóa');L()}
async function R(u){if(!confirm('Reset máy cho '+u+'? User sẽ cần gửi lại mã máy mới.'))return;await fetch(A+'/admin/users',{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify({username:u,reset_machine:true})});M('Đã reset máy');L()}
</script></body></html>`;
