const ADMIN_KEY = "huyem";
const PLAN_LIMITS = { trial: 10, basic: 50, premium: 200, unlimited: -1 };
function cors(h = {}) {
  return { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS", "Access-Control-Allow-Headers": "Content-Type,X-Admin-Key", ...h };
}
function json(d, s = 200) { return Response.json(d, { status: s, headers: cors() }); }
let _m = false;
async function mig(db) {
  if (_m) return; _m = true;
  try { await db.prepare("SELECT video_limit FROM app_users LIMIT 1").first(); }
  catch { await db.prepare("ALTER TABLE app_users ADD COLUMN video_limit INTEGER DEFAULT NULL").run(); await db.prepare("ALTER TABLE app_users ADD COLUMN videos_used INTEGER DEFAULT 0").run(); }
}
export default { async fetch(req, env) {
  const url = new URL(req.url), p = url.pathname.replace(/\/+$/, "") || "/";
  if (req.method === "OPTIONS") return new Response(null, { headers: cors() });
  await mig(env.DB);
  if (p === "/login" && req.method === "POST") {
    const { username, password, machine_id } = await req.json();
    if (!username || !password) return json({ ok: false, error: "Missing credentials" }, 400);
    const r = await env.DB.prepare("SELECT * FROM app_users WHERE username=?").bind(username).first();
    if (!r || r.password !== password) return json({ ok: false, error: "Sai tài khoản hoặc mật khẩu" }, 401);
    if (!r.is_active) return json({ ok: false, error: "Tài khoản đã bị khóa" }, 403);
    if (machine_id && r.machine_id && r.machine_id !== machine_id) return json({ ok: false, error: "Tài khoản đã được đăng ký trên máy khác. Liên hệ admin để reset." }, 403);
    if (machine_id && !r.machine_id) await env.DB.prepare("UPDATE app_users SET machine_id=? WHERE username=?").bind(machine_id, username).run();
    return json({ ok: true, username: r.username, plan: r.plan, expires_at: r.expires_at, video_limit: r.video_limit, videos_used: r.videos_used || 0 });
  }
  if (p === "/check" && req.method === "POST") {
    const { username, machine_id } = await req.json();
    if (!username) return json({ ok: false, error: "Missing username" }, 400);
    const r = await env.DB.prepare("SELECT * FROM app_users WHERE username=?").bind(username).first();
    if (!r) return json({ ok: false, error: "User not found" }, 404);
    if (!r.is_active) return json({ ok: false, expired: true, error: "Tài khoản đã bị khóa" });
    if (machine_id && r.machine_id && r.machine_id !== machine_id) return json({ ok: false, expired: true, error: "Tài khoản đang dùng trên máy khác" });
    const now = new Date().toISOString().split("T")[0], expired = r.expires_at && r.expires_at < now;
    return json({ ok: !expired, expired: !!expired, plan: r.plan, expires_at: r.expires_at, video_limit: r.video_limit, videos_used: r.videos_used || 0 });
  }
  if (p === "/check-limit" && req.method === "POST") {
    const { username } = await req.json();
    if (!username) return json({ ok: false, error: "Missing username" }, 400);
    const r = await env.DB.prepare("SELECT video_limit,videos_used,is_active FROM app_users WHERE username=?").bind(username).first();
    if (!r) return json({ ok: false, error: "User not found" }, 404);
    if (!r.is_active) return json({ ok: false, error: "Tài khoản đã bị khóa" });
    const used = r.videos_used || 0, lim = r.video_limit;
    return json({ ok: true, can_generate: lim === null || lim < 0 ? true : used < lim, video_limit: lim, videos_used: used, remaining: lim === null || lim < 0 ? null : Math.max(0, lim - used) });
  }
  if (p === "/record-usage" && req.method === "POST") {
    const { username, count } = await req.json();
    if (!username) return json({ ok: false, error: "Missing username" }, 400);
    await env.DB.prepare("UPDATE app_users SET videos_used=COALESCE(videos_used,0)+? WHERE username=?").bind(count || 1, username).run();
    const r = await env.DB.prepare("SELECT video_limit,videos_used FROM app_users WHERE username=?").bind(username).first();
    return json({ ok: true, videos_used: r?.videos_used || 0, video_limit: r?.video_limit });
  }
  if (p === "/admin") return new Response(ADMIN_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
  if (p === "/admin/users") {
    if (req.headers.get("X-Admin-Key") !== ADMIN_KEY) return json({ error: "Unauthorized" }, 401);
    if (req.method === "GET") {
      const { results } = await env.DB.prepare("SELECT username,plan,expires_at,is_active,machine_id,created_at,video_limit,videos_used FROM app_users ORDER BY created_at DESC").all();
      const now = new Date().toISOString().split("T")[0];
      return json({ users: results, stats: { total: results.length, active: results.filter(u => u.is_active && (!u.expires_at || u.expires_at >= now)).length, expired: results.filter(u => u.expires_at && u.expires_at < now).length, locked: results.filter(u => !u.is_active).length, totalUsed: results.reduce((s, u) => s + (u.videos_used || 0), 0) } });
    }
    if (req.method === "POST") {
      const b = await req.json(); if (!b.username || !b.password) return json({ error: "Missing fields" }, 400);
      const pl = b.plan || "trial", lim = b.video_limit != null && b.video_limit !== "" ? parseInt(b.video_limit) : (PLAN_LIMITS[pl] ?? 10);
      await env.DB.prepare("INSERT OR REPLACE INTO app_users (username,password,plan,expires_at,is_active,machine_id,video_limit,videos_used) VALUES(?,?,?,?,1,?,?,0)").bind(b.username, b.password, pl, b.expires_at || "", b.machine_id || null, lim).run();
      return json({ ok: true });
    }
    if (req.method === "PUT") {
      const b = await req.json(); if (!b.username) return json({ error: "Missing username" }, 400);
      const pts = [], vs = [];
      if (b.password != null && b.password !== "") { pts.push("password=?"); vs.push(b.password); }
      if (b.plan !== undefined) { pts.push("plan=?"); vs.push(b.plan); }
      if (b.expires_at !== undefined) { pts.push("expires_at=?"); vs.push(b.expires_at); }
      if (b.is_active !== undefined) { pts.push("is_active=?"); vs.push(b.is_active ? 1 : 0); }
      if (b.machine_id !== undefined) { pts.push("machine_id=?"); vs.push(b.machine_id); }
      if (b.reset_machine) pts.push("machine_id=NULL");
      if (b.video_limit != null && b.video_limit !== "") { pts.push("video_limit=?"); vs.push(parseInt(b.video_limit)); }
      if (b.reset_usage) pts.push("videos_used=0");
      if (!pts.length) return json({ error: "Nothing to update" }, 400);
      vs.push(b.username);
      await env.DB.prepare("UPDATE app_users SET " + pts.join(",") + " WHERE username=?").bind(...vs).run();
      return json({ ok: true });
    }
    if (req.method === "DELETE") {
      const u = url.searchParams.get("username"); if (!u) return json({ error: "Missing username" }, 400);
      await env.DB.prepare("DELETE FROM app_users WHERE username=?").bind(u).run();
      return json({ ok: true });
    }
  }
  if (p === "/admin/bulk" && req.method === "POST") {
    if (req.headers.get("X-Admin-Key") !== ADMIN_KEY) return json({ error: "Unauthorized" }, 401);
    const { action, usernames, value } = await req.json();
    if (!usernames || !usernames.length) return json({ error: "No users selected" }, 400);
    let c = 0;
    for (const u of usernames) {
      if (action === "delete") await env.DB.prepare("DELETE FROM app_users WHERE username=?").bind(u).run();
      else if (action === "lock") await env.DB.prepare("UPDATE app_users SET is_active=0 WHERE username=?").bind(u).run();
      else if (action === "unlock") await env.DB.prepare("UPDATE app_users SET is_active=1 WHERE username=?").bind(u).run();
      else if (action === "reset_machine") await env.DB.prepare("UPDATE app_users SET machine_id=NULL WHERE username=?").bind(u).run();
      else if (action === "reset_usage") await env.DB.prepare("UPDATE app_users SET videos_used=0 WHERE username=?").bind(u).run();
      else if (action === "set_limit") await env.DB.prepare("UPDATE app_users SET video_limit=? WHERE username=?").bind(parseInt(value) || 10, u).run();
      c++;
    }
    return json({ ok: true, count: c });
  }
  return json({ error: "Not found" }, 404);
}};

const ADMIN_HTML = '<!DOCTYPE html>\n<html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Grok Admin</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"><style>*{margin:0;padding:0;box-sizing:border-box}:root{--bg:#f5f6fa;--card:#fff;--bdr:#e8eaed;--o:#f97316;--ol:#fff7ed;--g:#22c55e;--gl:#f0fdf4;--pk:#ec4899;--pkl:#fdf2f8;--rd:#ef4444;--bl:#3b82f6;--t1:#1e293b;--t2:#64748b;--t3:#94a3b8;--sh:0 1px 3px rgba(0,0,0,.06);--r:12px}body{font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--t1);min-height:100vh;display:flex}.sidebar{width:230px;background:var(--card);border-right:1px solid var(--bdr);padding:20px 0;display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:10}.logo{display:flex;align-items:center;gap:10px;padding:0 20px 20px;border-bottom:1px solid var(--bdr);margin-bottom:8px}.logo-icon{width:36px;height:36px;background:linear-gradient(135deg,var(--o),#fb923c);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px}.logo span{font-weight:700;font-size:16px}.nav{flex:1;padding:8px 12px}.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;color:var(--t2);transition:all .15s;margin-bottom:2px;user-select:none}.nav-item:hover{background:var(--ol);color:var(--o)}.nav-item.active{background:var(--ol);color:var(--o);font-weight:600}.sidebar-footer{padding:16px 20px;border-top:1px solid var(--bdr);font-size:11px;color:var(--t3)}.main{margin-left:230px;flex:1;padding:24px 32px;min-height:100vh}.hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}.hdr h1{font-size:22px;font-weight:700}.hdr .sub{font-size:13px;color:var(--t2)}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px}.stat{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:20px;box-shadow:var(--sh)}.stat-ic{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:12px}.si-o{background:var(--ol)}.si-g{background:var(--gl)}.si-p{background:var(--pkl)}.si-b{background:#eff6ff}.stat-v{font-size:28px;font-weight:800}.stat-l{font-size:12px;color:var(--t2);margin-top:4px}.card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:24px;box-shadow:var(--sh);margin-bottom:20px}.card-h{font-size:15px;font-weight:600;margin-bottom:16px}.tw{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);overflow-x:auto;box-shadow:var(--sh)}table{width:100%;border-collapse:collapse}th{background:#fafbfc;padding:10px 12px;font-size:11px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:.5px;text-align:left;border-bottom:1px solid var(--bdr)}td{padding:10px 12px;font-size:13px;border-bottom:1px solid #f1f3f5;vertical-align:middle}tr:hover td{background:#fafbfc}.badge{display:inline-flex;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}.b-ok{background:var(--gl);color:var(--g)}.b-no{background:#fef2f2;color:var(--rd)}.b-ex{background:var(--ol);color:var(--o)}.b-pl{background:var(--pkl);color:var(--pk)}.vb{display:flex;align-items:center;gap:6px;font-size:12px}.vt{width:80px;height:6px;background:#f1f3f5;border-radius:3px;overflow:hidden}.vf{height:100%;border-radius:3px}.mid{font-size:11px;color:var(--t3);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.mid:hover{color:var(--t1)}.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;font-size:13px;font-weight:500;border:1px solid var(--bdr);background:var(--card);color:var(--t1);cursor:pointer;transition:all .15s;white-space:nowrap}.btn:hover{box-shadow:var(--sh)}.btn-o{background:var(--o);color:#fff;border-color:var(--o)}.btn-o:hover{background:#ea580c}.btn-g{background:var(--g);color:#fff;border-color:var(--g)}.btn-pk{background:var(--pk);color:#fff;border-color:var(--pk)}.btn-rd{background:var(--rd);color:#fff;border-color:var(--rd)}.btn-sm{padding:5px 10px;font-size:11px;border-radius:6px}.btn-ic{width:30px;height:30px;padding:0;display:inline-flex;align-items:center;justify-content:center;border-radius:6px;font-size:14px;border:1px solid var(--bdr);background:var(--card);cursor:pointer}.btn-ic:hover{background:#f9fafb}.sch{padding:8px 14px;border:1px solid var(--bdr);border-radius:8px;font-size:13px;background:var(--card);width:220px}.sch:focus{outline:none;border-color:var(--o)}.bb{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);margin-bottom:12px}.bb-l{font-size:12px;color:var(--t2)}.bb-a{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}.ckw{display:flex;align-items:center;cursor:pointer}.ckw input{width:16px;height:16px;accent-color:var(--o);cursor:pointer}.fg{display:grid;grid-template-columns:1fr 1fr;gap:16px}.fi label{display:block;font-size:12px;font-weight:500;color:var(--t2);margin-bottom:6px}.fi input,.fi select{width:100%;padding:9px 12px;border:1px solid var(--bdr);border-radius:8px;font-size:13px;font-family:inherit}.fi input:focus,.fi select:focus{outline:none;border-color:var(--o)}.tr{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid #f1f3f5}.tr:last-child{border:none}.tr-n{flex:1;font-size:13px;font-weight:500}.tr-b{width:120px;height:6px;background:#f1f3f5;border-radius:3px;overflow:hidden}.tr-f{height:100%;border-radius:3px}.tr-v{font-size:12px;font-weight:600;width:60px;text-align:right}.ac{display:flex;gap:4px}#toast{position:fixed;top:20px;right:20px;z-index:999;padding:12px 20px;border-radius:8px;font-size:13px;font-weight:500;display:none;box-shadow:0 4px 12px rgba(0,0,0,.1)}.t-ok{background:#dcfce7;color:#166534;border:1px solid #bbf7d0}.t-err{background:#fef2f2;color:#991b1b;border:1px solid #fecaca}@media(max-width:768px){.sidebar{display:none}.main{margin-left:0;padding:16px}.fg{grid-template-columns:1fr}}</style></head><body>' +
'<div class="sidebar"><div class="logo"><div class="logo-icon">🎬</div><span>Grok Admin</span></div><nav class="nav" id="navMenu"><div class="nav-item active" data-tab="dashboard">📊 Dashboard</div><div class="nav-item" data-tab="users">👥 Tài khoản</div><div class="nav-item" data-tab="adduser">➕ Thêm / Sửa</div></nav><div class="sidebar-footer">Grok Video Admin v2.1</div></div>' +
'<div class="main"><div id="toast"></div>' +
'<div id="tab-dashboard" class="tab"><div class="hdr"><div><h1>Dashboard</h1><div class="sub">Tổng quan hệ thống</div></div></div><div id="statsArea" class="stats"></div><div class="card" style="margin-top:4px"><div class="card-h">🎬 Top sử dụng video</div><div id="topUsage"></div></div></div>' +
'<div id="tab-users" class="tab" style="display:none"><div class="hdr"><div><h1>Quản lý tài khoản</h1><div class="sub" id="userCount"></div></div><div style="display:flex;gap:8px"><input class="sch" id="searchBox" placeholder="🔍 Tìm username..."><button class="btn btn-o" id="btnReload">🔄 Tải lại</button></div></div>' +
'<div class="bb"><label class="ckw"><input type="checkbox" id="selAll"></label><span class="bb-l" id="selLabel">Chọn tất cả</span><div class="bb-a" id="bulkActs" style="display:none"><button class="btn btn-sm btn-g" data-bulk="unlock">🔓 Mở khóa</button><button class="btn btn-sm btn-pk" data-bulk="lock">🔒 Khóa</button><button class="btn btn-sm" data-bulk="reset_machine">🔄 Reset máy</button><button class="btn btn-sm" data-bulk="reset_usage">📊 Reset video</button><button class="btn btn-sm" data-bulk="set_limit">📏 Set limit</button><button class="btn btn-sm btn-rd" data-bulk="delete">🗑️ Xóa</button></div></div>' +
'<div class="tw"><table><thead><tr><th style="width:36px"></th><th>Username</th><th>Gói</th><th>Video</th><th>Hết hạn</th><th>Trạng thái</th><th>Machine ID</th><th>Ngày tạo</th><th>Thao tác</th></tr></thead><tbody id="userList"></tbody></table></div></div>' +
'<div id="tab-adduser" class="tab" style="display:none"><div class="hdr"><div><h1>Thêm / Sửa tài khoản</h1><div class="sub">Tạo mới hoặc chỉnh sửa thông tin</div></div></div><div class="card" style="max-width:640px"><div class="fg"><div class="fi"><label>Username</label><input id="fu" placeholder="username"></div><div class="fi"><label>Password</label><input id="fp" placeholder="bỏ trống nếu chỉ sửa"></div><div class="fi"><label>Gói</label><select id="fpl"><option value="trial">Trial (10 video)</option><option value="basic">Basic (50 video)</option><option value="premium">Premium (200 video)</option><option value="unlimited">Unlimited</option></select></div><div class="fi"><label>Hết hạn</label><input id="fe" type="date"></div><div class="fi"><label>Video Limit</label><input id="fvl" type="number" placeholder="Trống = theo gói" min="0"></div><div class="fi"><label>Machine ID</label><input id="fm" placeholder="tùy chọn"></div></div><div style="display:flex;gap:10px;margin-top:20px"><button class="btn btn-o" id="btnSave">💾 Lưu</button><button class="btn" id="btnClear">🗑️ Xóa form</button></div></div></div>' +
'</div>' +
'<script>' +
'var API=location.origin,KEY="huyem",users=[],sel=new Set();' +
'function toast(t,ok){var e=document.getElementById("toast");e.textContent=t;e.className=ok!==false?"t-ok":"t-err";e.style.display="block";setTimeout(function(){e.style.display="none"},3000)}' +
'function showTab(id){var tabs=document.querySelectorAll(".tab");for(var i=0;i<tabs.length;i++)tabs[i].style.display="none";var t=document.getElementById("tab-"+id);if(t)t.style.display="block";var navs=document.querySelectorAll(".nav-item");for(var i=0;i<navs.length;i++){if(navs[i].getAttribute("data-tab")===id)navs[i].classList.add("active");else navs[i].classList.remove("active")}}' +
'function esc(s){if(!s)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}' +
'function findU(u){for(var i=0;i<users.length;i++){if(users[i].username===u)return users[i]}return null}' +
'function updBulk(){document.getElementById("selLabel").textContent=sel.size?sel.size+" đã chọn":"Chọn tất cả";document.getElementById("bulkActs").style.display=sel.size?"flex":"none"}' +
'function updStats(){var total=users.length,active=0,totalV=0,expired=0,now=new Date().toISOString().split("T")[0];for(var i=0;i<users.length;i++){if(users[i].is_active)active++;totalV+=(users[i].videos_used||0);if(users[i].expires_at&&users[i].expires_at<now)expired++}' +
'document.getElementById("statsArea").innerHTML=' +
'"<div class=stat><div class=\\"stat-ic si-o\\">👥</div><div class=stat-v>"+total+"</div><div class=stat-l>Tổng tài khoản</div></div>"+"<div class=stat><div class=\\"stat-ic si-g\\">✅</div><div class=stat-v>"+active+"</div><div class=stat-l>Đang hoạt động</div></div>"+"<div class=stat><div class=\\"stat-ic si-p\\">🎬</div><div class=stat-v>"+totalV+"</div><div class=stat-l>Tổng video</div></div>"+"<div class=stat><div class=\\"stat-ic si-b\\">🔒</div><div class=stat-v>"+(total-active)+"</div><div class=stat-l>Khóa / "+expired+" hết hạn</div></div>";' +
'var sorted=users.slice().sort(function(a,b){return(b.videos_used||0)-(a.videos_used||0)}).slice(0,8);var maxV=1;for(var i=0;i<sorted.length;i++){if((sorted[i].videos_used||0)>maxV)maxV=sorted[i].videos_used}var h="";for(var i=0;i<sorted.length;i++){var u=sorted[i],v=u.videos_used||0,pct=Math.round(v/maxV*100),lim=(u.video_limit!=null)?" / "+u.video_limit:"",color=(u.video_limit!=null&&v>=u.video_limit)?"var(--rd)":"var(--o)";h+="<div class=tr><div class=tr-n>"+esc(u.username)+"</div><div class=tr-b><div class=tr-f style=\\"width:"+pct+"%;background:"+color+"\\"></div></div><div class=tr-v style=color:"+color+">"+v+lim+"</div></div>"}document.getElementById("topUsage").innerHTML=h||"<div style=\\"color:var(--t3);font-size:13px;padding:8px\\">Chưa có dữ liệu</div>"}' +
'function renderUsers(list){var now=new Date().toISOString().split("T")[0],h="";for(var i=0;i<list.length;i++){var u=list[i],exp=u.expires_at&&u.expires_at<now,st=!u.is_active?"no":exp?"ex":"ok",sl=st==="ok"?"Hoạt động":st==="ex"?"Hết hạn":"Khóa",mid=u.machine_id||"",midS=mid?mid.slice(0,12)+"...":"—",ck=sel.has(u.username)?"checked":"",used=u.videos_used||0,lim=u.video_limit,hasLim=lim!=null&&lim>=0,pct=hasLim?Math.min(100,Math.round(used/Math.max(lim,1)*100)):0,vc=hasLim&&used>=lim?"var(--rd)":hasLim&&pct>70?"var(--o)":"var(--g)",vt=hasLim?used+"/"+lim:used+" / ∞";' +
'h+="<tr><td><label class=ckw><input type=checkbox class=uc data-u=\\""+esc(u.username)+"\\" "+ck+"></label></td>";' +
'h+="<td style=font-weight:500>"+esc(u.username)+"</td>";' +
'h+="<td><span class=\\"badge b-pl\\">"+(u.plan||"trial")+"</span></td>";' +
'h+="<td><div class=vb><span style=\\"color:"+vc+";font-weight:600\\">"+vt+"</span>";' +
'if(hasLim)h+="<div class=vt><div class=vf style=\\"width:"+pct+"%;background:"+vc+"\\"></div></div>";' +
'h+="</div></td>";' +
'h+="<td>"+(u.expires_at||"∞")+"</td>";' +
'h+="<td><span class=\\"badge b-"+st+"\\">"+sl+"</span></td>";' +
'h+="<td class=mid title=\\""+esc(mid)+"\\" data-copy=\\""+esc(mid)+"\\">"+esc(midS)+"</td>";' +
'h+="<td style=\\"font-size:12px;color:var(--t3)\\">"+(u.created_at||"").slice(0,10)+"</td>";' +
'h+="<td><div class=ac>";' +
'h+="<button class=btn-ic data-act=edit data-user=\\""+esc(u.username)+"\\">✏️</button>";' +
'h+="<button class=btn-ic data-act=toggle data-user=\\""+esc(u.username)+"\\" data-active="+(u.is_active?1:0)+">"+(u.is_active?"🔒":"🔓")+"</button>";' +
'if(mid)h+="<button class=btn-ic data-act=resetm data-user=\\""+esc(u.username)+"\\">🔄</button>";' +
'h+="<button class=btn-ic data-act=del data-user=\\""+esc(u.username)+"\\">🗑️</button>";' +
'h+="</div></td></tr>"}' +
'document.getElementById("userList").innerHTML=h||"<tr><td colspan=9 style=\\"text-align:center;color:var(--t3);padding:40px\\">Không có tài khoản</td></tr>";document.getElementById("userCount").textContent=list.length+" tài khoản"}' +
'function filterUsers(){var q=document.getElementById("searchBox").value.toLowerCase();if(!q){renderUsers(users);return}var f=[];for(var i=0;i<users.length;i++){if(users[i].username.toLowerCase().indexOf(q)>=0)f.push(users[i])}renderUsers(f)}' +
'function loadUsers(){fetch(API+"/admin/users",{headers:{"X-Admin-Key":KEY}}).then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(function(d){users=d.users||[];renderUsers(users);updStats();updBulk()}).catch(function(e){toast("Lỗi: "+e.message,false)})}' +
'function bulkAction(act){if(!sel.size){toast("Chưa chọn user",false);return}var names={delete:"xóa",lock:"khóa",unlock:"mở khóa",reset_machine:"reset máy",reset_usage:"reset video",set_limit:"set limit"},val;if(act==="set_limit"){val=prompt("Video limit cho "+sel.size+" user:");if(val===null)return}else{if(!confirm((names[act]||act)+" "+sel.size+" tài khoản?"))return}fetch(API+"/admin/bulk",{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Key":KEY},body:JSON.stringify({action:act,usernames:Array.from(sel),value:val})}).then(function(r){return r.json()}).then(function(d){if(d.ok){toast("Đã "+(names[act]||act)+" "+d.count+" tài khoản");sel.clear();loadUsers()}else toast(d.error||"Lỗi",false)}).catch(function(e){toast("Lỗi: "+e.message,false)})}' +
'function saveUser(){var u=document.getElementById("fu").value.trim(),pw=document.getElementById("fp").value.trim(),m=document.getElementById("fm").value.trim(),vl=document.getElementById("fvl").value;if(!u){toast("Nhập username",false);return}var b={username:u,plan:document.getElementById("fpl").value,expires_at:document.getElementById("fe").value};if(m)b.machine_id=m;if(vl!=="")b.video_limit=parseInt(vl);if(pw)b.password=pw;fetch(API+"/admin/users",{method:pw?"POST":"PUT",headers:{"Content-Type":"application/json","X-Admin-Key":KEY},body:JSON.stringify(b)}).then(function(r){return r.json()}).then(function(d){if(d.ok){toast(pw?"Đã tạo!":"Đã cập nhật!");loadUsers();clearForm()}else toast(d.error||"Lỗi",false)}).catch(function(e){toast("Lỗi: "+e.message,false)})}' +
'function clearForm(){document.getElementById("fu").value="";document.getElementById("fp").value="";document.getElementById("fm").value="";document.getElementById("fvl").value="";document.getElementById("fe").value="";document.getElementById("fpl").selectedIndex=0}' +
'function editUser(username){var u=findU(username);if(!u)return;showTab("adduser");document.getElementById("fu").value=u.username;document.getElementById("fm").value=u.machine_id||"";document.getElementById("fvl").value=(u.video_limit!=null)?u.video_limit:"";document.getElementById("fpl").value=u.plan||"trial";document.getElementById("fe").value=u.expires_at||"";document.getElementById("fp").value="";document.getElementById("fp").focus()}' +
'function toggleActive(username,cur){fetch(API+"/admin/users",{method:"PUT",headers:{"Content-Type":"application/json","X-Admin-Key":KEY},body:JSON.stringify({username:username,is_active:!cur})}).then(function(r){return r.json()}).then(function(d){if(d.ok){toast(cur?"Đã khóa":"Đã mở khóa");loadUsers()}else toast(d.error||"Lỗi",false)})}' +
'function resetMachine(username){if(!confirm("Reset máy "+username+"?"))return;fetch(API+"/admin/users",{method:"PUT",headers:{"Content-Type":"application/json","X-Admin-Key":KEY},body:JSON.stringify({username:username,reset_machine:true})}).then(function(r){return r.json()}).then(function(d){if(d.ok){toast("Đã reset");loadUsers()}else toast(d.error||"Lỗi",false)})}' +
'function deleteUser(username){if(!confirm("Xóa "+username+"?"))return;fetch(API+"/admin/users?username="+encodeURIComponent(username),{method:"DELETE",headers:{"X-Admin-Key":KEY}}).then(function(r){return r.json()}).then(function(d){if(d.ok){toast("Đã xóa");loadUsers()}else toast(d.error||"Lỗi",false)})}' +
'document.addEventListener("click",function(e){var t=e.target,n=t.closest?t.closest(".nav-item"):null;if(n){var tab=n.getAttribute("data-tab");if(tab)showTab(tab);return}var bb=t.closest?t.closest("[data-bulk]"):null;if(bb){bulkAction(bb.getAttribute("data-bulk"));return}var ab=t.closest?t.closest("[data-act]"):null;if(ab){var a=ab.getAttribute("data-act"),u=ab.getAttribute("data-user");if(a==="edit")editUser(u);else if(a==="toggle")toggleActive(u,parseInt(ab.getAttribute("data-active")));else if(a==="resetm")resetMachine(u);else if(a==="del")deleteUser(u);return}var mc=t.closest?t.closest(".mid[data-copy]"):null;if(mc){var v=mc.getAttribute("data-copy");if(v&&navigator.clipboard){navigator.clipboard.writeText(v);toast("Copied!")}}});' +
'document.addEventListener("change",function(e){var t=e.target;if(t.id==="selAll"){var cbs=document.querySelectorAll(".uc");for(var i=0;i<cbs.length;i++){cbs[i].checked=t.checked;if(t.checked)sel.add(cbs[i].getAttribute("data-u"));else sel.delete(cbs[i].getAttribute("data-u"))}updBulk();return}if(t.classList&&t.classList.contains("uc")){var u=t.getAttribute("data-u");if(t.checked)sel.add(u);else sel.delete(u);updBulk()}});' +
'document.getElementById("searchBox").addEventListener("input",filterUsers);' +
'document.getElementById("btnReload").addEventListener("click",loadUsers);' +
'document.getElementById("btnSave").addEventListener("click",saveUser);' +
'document.getElementById("btnClear").addEventListener("click",clearForm);' +
'loadUsers();' +
'<\/script></body></html>';
