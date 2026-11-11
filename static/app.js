async function enablePush(){
 const out=document.getElementById("pushStatus"),say=t=>{if(out)out.textContent=t;else alert(t)};
 if(!("serviceWorker"in navigator)||!("PushManager"in window)){say("This browser does not support Web Push.");return}
 try{
  const k=await (await fetch("/api/push/key")).json();if(!k.publicKey){say("Push is not configured. Add VAPID keys to the server environment.");return}
  if(await Notification.requestPermission()!=="granted"){say("Notification permission was not granted.");return}
  const reg=await navigator.serviceWorker.register("/static/sw.js");
  const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:decodeKey(k.publicKey)});
  const r=await fetch("/api/push/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(sub)});
  if(!r.ok)throw Error("Could not save push subscription.");say("Push notifications enabled on this device.");
 }catch(e){say(e.message||"Push setup failed.");}
}
function decodeKey(s){let p="=".repeat((4-s.length%4)%4),b=atob((s+p).replace(/-/g,"+").replace(/_/g,"/"));return Uint8Array.from([...b].map(c=>c.charCodeAt(0)))}
