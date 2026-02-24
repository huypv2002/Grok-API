const ADMIN_KEY = "huyem";
function cors(h = {}) {
  return { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS", "Access-Control-Allow-Headers": "Content-Type,X-Admin-Key", ...h };
}
function json(data, status = 200) { return Response.json(data, { status, headers: cors() }); }

async function ensureSchema(db) {
  try { await db.prepare("ALTER TABLE app_users ADD COLUMN video_limit INTEGER DEFAULT NULL").run(); } catch {}
  try { await db.prepare("ALTER TABLE app_users ADD COLUMN videos_used INTEGER DEFAULT 0").run(); } catch {}
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (request.method === "OPTIONS") return new Response(null, { headers: cors() });
    await ensureSchema(env.DB);

    if (path === "/login" && request.method === "POST") {
      const { username, password, machine_id } = await request.json();
      if (!username || !password) return json({ ok: false, error: "Missing credentials" }, 400);
      const row = await env.DB.prepare("SELECT username,password,plan,expires_at,is_active,machine_id,video_limit,videos_used FROM app_users WHERE username=?").bind(username).first();
      if (!row || row.password !== password) return json({ ok: false, error: "Sai tài khoản hoặc mật khẩu" }, 401);
      if (!row.is_active) return json({ ok: false, error: "Tài khoản đã bị khóa" }, 403);
      if (machine_id && row.machine_id && row.machine_id !== machine_id) return json({ ok: false, error: "Tài khoản đã được đăng ký trên máy khác. Liên hệ admin để reset." }, 403);
      if (machine_id && !row.machine_id) await env.DB.prepare("UPDATE app_users SET machine_id=? WHERE username=?").bind(machine_id, username).run();
      return json({ ok: true, username: row.username, plan: row.plan, expires_at: row.expires_at, video_limit: row.video_limit, videos_used: row.videos_used || 0 });
    }

    if (path === "/check" && request.method === "POST") {
      const { username, machine_id } = await request.json();
      if (!username) return json({ ok: false, error: "Missing username" }, 400);
      const row = await env.DB.prepare("SELECT username,plan,expires_at,is_active,machine_id,video_limit,videos_used FROM app_users WHERE username=?").bind(username).first();
      if (!row) return json({ ok: false, error: "User not found" }, 404);
      if (!row.is_active) return json({ ok: false, expired: true, error: "Tài khoản đã bị khóa" });
      if (machine_id && row.machine_id && row.machine_id !== machine_id) return json({ ok: false, expired: true, error: "Tài khoản đang dùng trên máy khác" });
      const now = new Date().toISOString().split("T")[0];
      const expired = row.expires_at && row.expires_at < now;
      return json({ ok: !expired, expired: !!expired, plan: row.plan, expires_at: row.expires_at, video_limit: row.video_limit, videos_used: row.videos_used || 0 });
    }

    if (path === "/check-limit" && request.method === "POST") {
      const { username } = await request.json();
      if (!username) return json({ ok: false, error: "Missing username" }, 400);
      const row = await env.DB.prepare("SELECT video_limit,videos_used,is_active FROM app_users WHERE username=?").bind(username).first();
      if (!row) return json({ ok: false, error: "User not found" }, 404);
      if (!row.is_active) return json({ ok: false, error: "Tài khoản đã bị khóa" });
      const used = row.videos_used || 0, limit = row.video_limit;
      return json({ ok: true, can_generate: limit === null ? true : used < limit, video_limit: limit, videos_used: used, remaining: limit === null ? null : Math.max(0, limit - used) });
    }

    if (path === "/record-usage" && request.method === "POST") {
      const { username, count } = await request.json();
      if (!username) return json({ ok: false, error: "Missing username" }, 400);
      await env.DB.prepare("UPDATE app_users SET videos_used=COALESCE(videos_used,0)+? WHERE username=?").bind(count || 1, username).run();
      const row = await env.DB.prepare("SELECT video_limit,videos_used FROM app_users WHERE username=?").bind(username).first();
      return json({ ok: true, videos_used: row?.videos_used || 0, video_limit: row?.video_limit });
    }

    if (path === "/admin") return new Response(ADMIN_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });

    if (path === "/admin/users") {
      if (request.headers.get("X-Admin-Key") !== ADMIN_KEY) return json({ error: "Unauthorized" }, 401);
      if (request.method === "GET") {
        const { results } = await env.DB.prepare("SELECT username,plan,expires_at,is_active,machine_id,created_at,video_limit,videos_used FROM app_users ORDER BY created_at DESC").all();
        return json({ users: results });
      }
      if (request.method === "POST") {
        const { username, password, plan, expires_at, machine_id, video_limit } = await request.json();
        if (!username || !password) return json({ error: "Missing fields" }, 400);
        const vl = video_limit === "" || video_limit === undefined ? null : parseInt(video_limit);
        await env.DB.prepare("INSERT OR REPLACE INTO app_users (username,password,plan,expires_at,is_active,machine_id,video_limit,videos_used) VALUES(?,?,?,?,1,?,?,0)").bind(username, password, plan || "trial", expires_at || "", machine_id || null, vl).run();
        return json({ ok: true });
      }
      if (request.method === "PUT") {
        const { username, password, plan, expires_at, is_active, machine_id, reset_machine, video_limit, videos_used, reset_usage } = await request.json();
        if (!username) return json({ error: "Missing username" }, 400);
        const parts = [], vals = [];
        if (password !== undefined) { parts.push("password=?"); vals.push(password); }
        if (plan !== undefined) { parts.push("plan=?"); vals.push(plan); }
        if (expires_at !== undefined) { parts.push("expires_at=?"); vals.push(expires_at); }
        if (is_active !== undefined) { parts.push("is_active=?"); vals.push(is_active ? 1 : 0); }
        if (machine_id !== undefined) { parts.push("machine_id=?"); vals.push(machine_id); }
        if (reset_machine) { parts.push("machine_id=NULL"); }
        if (video_limit !== undefined) { const vl = video_limit === "" || video_limit === null ? null : parseInt(video_limit); parts.push("video_limit=?"); vals.push(vl); }
        if (videos_used !== undefined) { parts.push("videos_used=?"); vals.push(parseInt(videos_used)); }
        if (reset_usage) { parts.push("videos_used=0"); }
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

    if (path === "/admin/bulk" && request.method === "POST") {
      if (request.headers.get("X-Admin-Key") !== ADMIN_KEY) return json({ error: "Unauthorized" }, 401);
      const { action, usernames, value } = await request.json();
      if (!usernames || !usernames.length) return json({ error: "No users selected" }, 400);
      let count = 0;
      for (const u of usernames) {
        if (action === "delete") await env.DB.prepare("DELETE FROM app_users WHERE username=?").bind(u).run();
        else if (action === "lock") await env.DB.prepare("UPDATE app_users SET is_active=0 WHERE username=?").bind(u).run();
        else if (action === "unlock") await env.DB.prepare("UPDATE app_users SET is_active=1 WHERE username=?").bind(u).run();
        else if (action === "reset_machine") await env.DB.prepare("UPDATE app_users SET machine_id=NULL WHERE username=?").bind(u).run();
        else if (action === "reset_usage") await env.DB.prepare("UPDATE app_users SET videos_used=0 WHERE username=?").bind(u).run();
        else if (action === "set_limit") { const vl = value === "" || value === null || value === undefined ? null : parseInt(value); await env.DB.prepare("UPDATE app_users SET video_limit=? WHERE username=?").bind(vl, u).run(); }
        count++;
      }
      return json({ ok: true, count });
    }

    return json({ error: "Not found" }, 404);
  },
};

const ADMIN_HTML = `<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grok Admin Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f5f6fa;--card:#fff;--border:#e8eaed;--orange:#f97316;--orange-l:#fff7ed;--green:#22c55e;--green-l:#f0fdf4;--pink:#ec4899;--pink-l:#fdf2f8;--red:#ef4444;--blue:#3b82f6;--txt:#1e293b;--txt2:#64748b;--txt3:#94a3b8;--sh:0 1px 3px rgba(0,0,0,.06);--sh2:0 4px 16px rgba(0,0,0,.08);--r:12px}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--txt);min-height:100vh;display:flex}
.sidebar{width:240px;background:#fff;border-right:1px solid var(--border);padding:20px 0;display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:10}
.logo{display:flex;align-items:center;gap:10px;padding:0 20px 24px;border-bottom:1px solid var(--border);margin-bottom:8px}
.logo-icon{width:36px;height:36px;background:linear-gradient(135deg,var(--orange),#fb923c);border-radius:10px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:18px}
.logo span{font-weight:700;font-size:16px;color:var(--txt)}
.nav{flex:1;padding:8px 12px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;color:var(--txt2);text-decoration:none;transition:all .15s;margin-bottom:2px}
.nav-item:hover{background:var(--orange-l);color:var(--orange)}
.nav-item.active{background:var(--orange-l);color:var(--orange);font-weight:600}
.sidebar-footer{padding:16px 20px;border-top:1px solid var(--border);font-size:11px;color:var(--txt3)}
.main{margin-left:240px;flex:1;padding:24px 32px;min-height:100vh}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}
.header h1{font-size:22px;font-weight:700}
.header .sub{font-size:13px;color:var(--txt2)}
#toast{position:fixed;top:20px;right:20px;z-index:999;padding:12px 20px;border-radius:8px;font-size:13px;font-weight:500;display:none;box-shadow:var(--sh2)}
.toast-ok{background:#dcfce7;color:#166534;border:1px solid #bbf7d0}
.toast-err{background:#fef2f2;color:#991b1b;border:1px solid #fecaca}
</style>
</head><body>
<div class="sidebar">
<div class="logo"><div class="logo-icon">G</div><span>Grok Admin</span></div>
<nav class="nav">
<a class="nav-item active" data-tab="dashboard" onclick="showTab('dashboard',this)"><svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>Dashboard</a>
<a class="nav-item" data-tab="users" onclick="showTab('users',this)"><svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/></svg>Tài khoản</a>
<a class="nav-item" data-tab="adduser" onclick="showTab('adduser',this)"><svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>Thêm / Sửa</a>
</nav>
<div class="sidebar-footer">v2.0 — Video Limit</div>
</div>
<div class="main">
<div id="toast"></div>

<!-- DASHBOARD TAB -->
<div id="tab-dashboard" class="tab">
<div class="header"><div><h1>Dashboard</h1><div class="sub">Tổng quan hệ thống</div></div></div>
<div class="stats" id="stats"></div>
<div class="card" style="margin-top:20px"><div class="card-h">Top sử dụng video</div><div id="topUsage"></div></div>
</div>

<!-- USERS TAB -->
<div id="tab-users" class="tab" style="display:none">
<div class="header"><div><h1>Quản lý tài khoản</h1><div class="sub" id="userCount"></div></div>
<div style="display:flex;gap:8px"><input class="search" id="searchBox" placeholder="Tìm username..." oninput="filterUsers()"><button class="btn btn-o" onclick="L()">Tải lại</button></div></div>
<div class="bulk-bar">
<label class="ck-wrap"><input type="checkbox" id="selAll" onchange="selAllToggle(this.checked)"><span class="ck-box"></span></label>
<span class="bulk-label" id="selLabel">Chọn tất cả</span>
<div class="bulk-actions" id="bulkActions" style="display:none">
<button class="btn btn-sm btn-green" onclick="BA('unlock')">Mở khóa</button>
<button class="btn btn-sm btn-pink" onclick="BA('lock')">Khóa</button>
<button class="btn btn-sm" onclick="BA('reset_machine')">Reset máy</button>
<button class="btn btn-sm" onclick="BA('reset_usage')">Reset video</button>
<button class="btn btn-sm" onclick="promptBulkLimit()">Set limit</button>
<button class="btn btn-sm btn-red" onclick="BA('delete')">Xóa</button>
</div>
</div>
<div class="table-wrap"><table><thead><tr>
<th style="width:36px"></th><th>Username</th><th>Gói</th><th>Video</th><th>Hết hạn</th><th>Trạng thái</th><th>Machine ID</th><th>Ngày tạo</th><th>Thao tác</th>
</tr></thead><tbody id="userList"></tbody></table></div>
</div>

<!-- ADD/EDIT TAB -->
<div id="tab-adduser" class="tab" style="display:none">
<div class="header"><div><h1>Thêm / Sửa tài khoản</h1><div class="sub">Tạo mới hoặc chỉnh sửa thông tin</div></div></div>
<div class="card" style="max-width:640px">
<div class="form-grid">
<div class="fg"><label>Username</label><input id="fu" placeholder="username"></div>
<div class="fg"><label>Password</label><input id="fp" placeholder="password (bỏ trống nếu chỉ sửa)"></div>
<div class="fg"><label>Gói</label><select id="fpl"><option value="trial">Trial</option><option value="basic">Basic</option><option value="premium">Premium</option></select></div>
<div class="fg"><label>Hết hạn</label><input id="fe" type="date"></div>
<div class="fg"><label>Video Limit</label><input id="fvl" type="number" placeholder="Trống = không giới hạn" min="0"></div>
<div class="fg"><label>Machine ID</label><input id="fm" placeholder="Mã máy (tùy chọn)"></div>
</div>
<div style="display:flex;gap:10px;margin-top:20px">
<button class="btn btn-o" onclick="saveUser()">Lưu tài khoản</button>
<button class="btn" onclick="clearForm()">Xóa form</button>
</div>
</div>
</div>
</div>
<style>
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;box-shadow:var(--sh)}
.stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:12px}
.stat-icon.orange{background:var(--orange-l);color:var(--orange)}
.stat-icon.green{background:var(--green-l);color:var(--green)}
.stat-icon.pink{background:var(--pink-l);color:var(--pink)}
.stat-icon.blue{background:#eff6ff;color:var(--blue)}
.stat-val{font-size:28px;font-weight:800;line-height:1}
.stat-label{font-size:12px;color:var(--txt2);margin-top:4px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:24px;box-shadow:var(--sh)}
.card-h{font-size:15px;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;box-shadow:var(--sh)}
table{width:100%;border-collapse:collapse}
th{background:#fafbfc;padding:10px 12px;font-size:11px;font-weight:600;color:var(--txt2);text-transform:uppercase;letter-spacing:.5px;text-align:left;border-bottom:1px solid var(--border)}
td{padding:10px 12px;font-size:13px;border-bottom:1px solid #f1f3f5;vertical-align:middle}
tr:hover td{background:#fafbfc}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
.badge-ok{background:var(--green-l);color:var(--green)}
.badge-no{background:#fef2f2;color:var(--red)}
.badge-ex{background:var(--orange-l);color:var(--orange)}
.badge-plan{background:var(--pink-l);color:var(--pink)}
.vid-bar{display:flex;align-items:center;gap:6px;font-size:12px}
.vid-track{width:80px;height:6px;background:#f1f3f5;border-radius:3px;overflow:hidden}
.vid-fill{height:100%;border-radius:3px;transition:width .3s}
.mid{font-size:11px;color:var(--txt3);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
.mid:hover{color:var(--txt)}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;font-size:13px;font-weight:500;border:1px solid var(--border);background:var(--card);color:var(--txt);cursor:pointer;transition:all .15s;white-space:nowrap}
.btn:hover{box-shadow:var(--sh);border-color:#d1d5db}
.btn-o{background:var(--orange);color:#fff;border-color:var(--orange)}.btn-o:hover{background:#ea580c}
.btn-green{background:var(--green);color:#fff;border-color:var(--green)}
.btn-pink{background:var(--pink);color:#fff;border-color:var(--pink)}
.btn-red{background:var(--red);color:#fff;border-color:var(--red)}
.btn-sm{padding:5px 10px;font-size:11px;border-radius:6px}
.btn-icon{width:30px;height:30px;padding:0;display:inline-flex;align-items:center;justify-content:center;border-radius:6px;font-size:14px}
.search{padding:8px 14px;border:1px solid var(--border);border-radius:8px;font-size:13px;background:var(--card);color:var(--txt);width:220px}
.search:focus{outline:none;border-color:var(--orange);box-shadow:0 0 0 3px rgba(249,115,22,.1)}
.bulk-bar{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--card);border:1px solid var(--border);border-radius:var(--r);margin-bottom:12px;box-shadow:var(--sh)}
.bulk-label{font-size:12px;color:var(--txt2)}
.bulk-actions{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
.ck-wrap{display:flex;align-items:center;cursor:pointer}
.ck-wrap input{display:none}
.ck-box{width:18px;height:18px;border:2px solid #d1d5db;border-radius:4px;display:flex;align-items:center;justify-content:center;transition:all .15s}
.ck-wrap input:checked+.ck-box{background:var(--orange);border-color:var(--orange);color:#fff}
.ck-wrap input:checked+.ck-box::after{content:'\\2713';font-size:12px;font-weight:700;color:#fff}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.fg label{display:block;font-size:12px;font-weight:500;color:var(--txt2);margin-bottom:6px}
.fg input,.fg select{width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px;background:var(--card);color:var(--txt)}
.fg input:focus,.fg select:focus{outline:none;border-color:var(--orange);box-shadow:0 0 0 3px rgba(249,115,22,.1)}
.top-row{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid #f1f3f5}
.top-row:last-child{border:none}
.top-name{flex:1;font-size:13px;font-weight:500}
.top-bar{width:120px;height:6px;background:#f1f3f5;border-radius:3px;overflow:hidden}
.top-fill{height:100%;border-radius:3px}
.top-val{font-size:12px;font-weight:600;width:60px;text-align:right}
@media(max-width:768px){.sidebar{display:none}.main{margin-left:0;padding:16px}.form-grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}
</style>
<script>
const A=location.origin,K=()=>'huyem';
let users=[],sel=new Set();

function toast(t,ok=true){const e=document.getElementById('toast');e.textContent=t;e.className=ok?'toast-ok':'toast-err';e.style.display='block';setTimeout(()=>e.style.display='none',3000)}
function showTab(id,el){document.querySelectorAll('.tab').forEach(t=>t.style.display='none');document.getElementById('tab-'+id).style.display='block';document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));if(el)el.classList.add('active');else document.querySelector('[data-tab="'+id+'"]')?.classList.add('active')}

function updateStats(){
  const total=users.length,active=users.filter(u=>u.is_active).length,locked=total-active;
  const now=new Date().toISOString().split('T')[0];
  const expired=users.filter(u=>u.expires_at&&u.expires_at<now).length;
  const totalVids=users.reduce((s,u)=>s+(u.videos_used||0),0);
  const limited=users.filter(u=>u.video_limit!==null&&u.video_limit!==undefined).length;
  document.getElementById('stats').innerHTML=
    '<div class="stat"><div class="stat-icon orange">👥</div><div class="stat-val">'+total+'</div><div class="stat-label">Tổng tài khoản</div></div>'+
    '<div class="stat"><div class="stat-icon green">✅</div><div class="stat-val">'+active+'</div><div class="stat-label">Đang hoạt động</div></div>'+
    '<div class="stat"><div class="stat-icon pink">🎬</div><div class="stat-val">'+totalVids+'</div><div class="stat-label">Tổng video đã tạo</div></div>'+
    '<div class="stat"><div class="stat-icon blue">🔒</div><div class="stat-val">'+locked+'</div><div class="stat-label">Đã khóa / '+expired+' hết hạn</div></div>';
  // Top usage
  const sorted=[...users].sort((a,b)=>(b.videos_used||0)-(a.videos_used||0)).slice(0,8);
  const maxV=Math.max(...sorted.map(u=>u.videos_used||0),1);
  let topH='';
  sorted.forEach(u=>{
    const v=u.videos_used||0,pct=Math.round(v/maxV*100);
    const lim=u.video_limit!==null&&u.video_limit!==undefined?' / '+u.video_limit:'';
    const color=u.video_limit&&v>=u.video_limit?'var(--red)':'var(--orange)';
    topH+='<div class="top-row"><div class="top-name">'+u.username+'</div><div class="top-bar"><div class="top-fill" style="width:'+pct+'%;background:'+color+'"></div></div><div class="top-val" style="color:'+color+'">'+v+lim+'</div></div>';
  });
  document.getElementById('topUsage').innerHTML=topH||'<div style="color:var(--txt3);font-size:13px">Chưa có dữ liệu</div>';
}
function renderUsers(list){
  const now=new Date().toISOString().split('T')[0];
  let h='';
  list.forEach(u=>{
    const exp=u.expires_at&&u.expires_at<now;
    const st=!u.is_active?'no':exp?'ex':'ok';
    const sl=st==='ok'?'Hoạt động':st==='ex'?'Hết hạn':'Khóa';
    const mid=u.machine_id||'';
    const midS=mid?mid.slice(0,12)+'…':'—';
    const ck=sel.has(u.username)?'checked':'';
    const used=u.videos_used||0;
    const lim=u.video_limit;
    const hasLim=lim!==null&&lim!==undefined;
    const pct=hasLim?Math.min(100,Math.round(used/lim*100)):0;
    const vidColor=hasLim&&used>=lim?'var(--red)':hasLim&&pct>70?'var(--orange)':'var(--green)';
    const vidText=hasLim?used+'/'+lim:used+' / ∞';
    h+='<tr><td><label class="ck-wrap"><input type="checkbox" class="uc" data-u="'+u.username+'" '+ck+' onchange="toggleSel(this)"><span class="ck-box"></span></label></td>';
    h+='<td style="font-weight:500">'+u.username+'</td>';
    h+='<td><span class="badge badge-plan">'+( u.plan||'trial')+'</span></td>';
    h+='<td><div class="vid-bar"><span style="color:'+vidColor+';font-weight:600">'+vidText+'</span>';
    if(hasLim)h+='<div class="vid-track"><div class="vid-fill" style="width:'+pct+'%;background:'+vidColor+'"></div></div>';
    h+='</div></td>';
    h+='<td>'+(u.expires_at||'∞')+'</td>';
    h+='<td><span class="badge badge-'+st+'">'+sl+'</span></td>';
    h+='<td class="mid" title="'+mid+'" onclick="navigator.clipboard.writeText(\''+mid+'\');toast(\'Copied\')">'+midS+'</td>';
    h+='<td style="font-size:12px;color:var(--txt3)">'+(u.created_at||'').slice(0,10)+'</td>';
    h+='<td style="white-space:nowrap;display:flex;gap:4px">';
    h+='<button class="btn-icon btn" onclick="editUser(\''+u.username+'\',\''+mid+'\','+lim+')">✏️</button>';
    h+='<button class="btn-icon btn" style="color:var(--pink)" onclick="toggleActive(\''+u.username+'\','+(u.is_active?0:1)+')">'+(u.is_active?'🔒':'🔓')+'</button>';
    if(mid)h+='<button class="btn-icon btn" style="color:var(--blue)" onclick="resetMachine(\''+u.username+'\')">🔄</button>';
    h+='<button class="btn-icon btn" style="color:var(--red)" onclick="deleteUser(\''+u.username+'\')">🗑️</button>';
    h+='</td></tr>';
  });
  document.getElementById('userList').innerHTML=h||'<tr><td colspan="9" style="text-align:center;color:var(--txt3);padding:40px">Không có tài khoản nào</td></tr>';
}

function filterUsers(){const q=document.getElementById('searchBox').value.toLowerCase();renderUsers(q?users.filter(u=>u.username.toLowerCase().includes(q)):users)}
function selAllToggle(c){document.querySelectorAll('.uc').forEach(cb=>{cb.checked=c;c?sel.add(cb.dataset.u):sel.delete(cb.dataset.u)});updateBulk()}
function toggleSel(cb){cb.checked?sel.add(cb.dataset.u):sel.delete(cb.dataset.u);updateBulk()}
function updateBulk(){document.getElementById('selLabel').textContent=sel.size?sel.size+' đã chọn':'Chọn tất cả';document.getElementById('bulkActions').style.display=sel.size?'flex':'none'}
async function L(){
  const r=await fetch(A+'/admin/users',{headers:{'X-Admin-Key':K()}});
  if(!r.ok){toast('Lỗi tải dữ liệu',false);return}
  const d=await r.json();users=d.users||[];
  document.getElementById('userCount').textContent=users.length+' tài khoản';
  renderUsers(users);updateStats();updateBulk();
}

async function BA(act){
  if(!sel.size){toast('Chưa chọn user nào',false);return}
  const names={delete:'xóa',lock:'khóa',unlock:'mở khóa',reset_machine:'reset máy',reset_usage:'reset video'};
  if(!confirm((names[act]||act)+' '+sel.size+' tài khoản?'))return;
  const r=await fetch(A+'/admin/bulk',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify({action:act,usernames:[...sel]})});
  if(r.ok){const d=await r.json();toast('Đã '+names[act]+' '+d.count+' tài khoản');sel.clear();L()}else toast('Lỗi',false);
}

function promptBulkLimit(){
  if(!sel.size){toast('Chưa chọn user nào',false);return}
  const v=prompt('Nhập video limit cho '+sel.size+' user (trống = không giới hạn):');
  if(v===null)return;
  fetch(A+'/admin/bulk',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify({action:'set_limit',usernames:[...sel],value:v})}).then(r=>{if(r.ok){toast('Đã set limit');sel.clear();L()}else toast('Lỗi',false)});
}

async function saveUser(){
  const u=document.getElementById('fu').value.trim(),p=document.getElementById('fp').value.trim(),m=document.getElementById('fm').value.trim();
  const vl=document.getElementById('fvl').value;
  if(!u){toast('Nhập username',false);return}
  const b={username:u,plan:document.getElementById('fpl').value,expires_at:document.getElementById('fe').value};
  if(m)b.machine_id=m;
  if(vl!=='')b.video_limit=parseInt(vl);else b.video_limit='';
  if(p){
    b.password=p;
    const r=await fetch(A+'/admin/users',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify(b)});
    r.ok?toast('Đã tạo tài khoản!'):toast('Lỗi',false);
  }else{
    const r=await fetch(A+'/admin/users',{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify(b)});
    r.ok?toast('Đã cập nhật!'):toast('Lỗi',false);
  }
  L();clearForm();
}

function clearForm(){['fu','fp','fm','fvl','fe'].forEach(id=>document.getElementById(id).value='');document.getElementById('fpl').selectedIndex=0}
function editUser(u,mid,lim){showTab('adduser');document.getElementById('fu').value=u;document.getElementById('fm').value=mid||'';if(lim!==null&&lim!==undefined&&!isNaN(lim))document.getElementById('fvl').value=lim;document.getElementById('fp').focus()}
async function deleteUser(u){if(!confirm('Xóa '+u+'?'))return;await fetch(A+'/admin/users?username='+u,{method:'DELETE',headers:{'X-Admin-Key':K()}});toast('Đã xóa');L()}
async function toggleActive(u,a){await fetch(A+'/admin/users',{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify({username:u,is_active:!!a})});toast(a?'Đã mở khóa':'Đã khóa');L()}
async function resetMachine(u){if(!confirm('Reset máy cho '+u+'?'))return;await fetch(A+'/admin/users',{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':K()},body:JSON.stringify({username:u,reset_machine:true})});toast('Đã reset máy');L()}

L();
</script></body></html>`;
