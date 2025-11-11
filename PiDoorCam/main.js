// main.js - small client-side helper to remove 404 and surface simple status info
window.addEventListener('load', async () => {
  console.log('main.js loaded')
  try{
    const r = await fetch('/status')
    if(r.ok){
      const j = await r.json()
      console.log('server status', j)
      const el = document.createElement('div')
      el.style.fontSize = '12px'
      el.style.color = '#666'
      el.textContent = `camera_started=${j.pc2_started} last_frame_age_s=${j.last_frame_age_s} ws_clients=${j.ws_clients}`
      document.body.appendChild(el)
    }
  }catch(e){ console.warn('main.js: status fetch failed', e) }
})
