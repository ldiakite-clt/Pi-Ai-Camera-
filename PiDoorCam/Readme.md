Status summary: We now have a 4-page static site ready for the ZIP and Canvas link: index.html (overview), live.html (shows MJPEG at http://PI_IP:8080/stream.mjpg with placeholder fallback), heatmap.html (24 hourly buckets from /var/www/html/data/motion-today.json with fallback sample), and access.html (hotspot and security notes). Nav/CSS/JS are wired and consistent; extra credit items are in (sticky nav, active-page highlight, responsive layout, heatmap fallback). Plan is MJPEG for submission; WebRTC comes later (I’ll add a WebRTC-first then MJPEG fallback once signaling/HTTPS are in place). Hosting plan: Pi as WPA2-PSK hotspot (hostapd + dnsmasq), site on :80, stream on :8080. Next concrete steps: enable camera, run ustreamer or mjpg-streamer at ~640x360/10–15 fps, copy site to /var/www/html, create motion-today.json and add a nightly reset. Implications: MJPEG is bandwidth-heavy so keep resolution/FPS modest.

Layout: 

Home (index.html): overview hero + 3 minimal feature cards linking to the other pages.

Live (live.html): left = how it works, right = MJPEG <img> showing http://PI_IP:8080/stream.mjpg with placeholder fallback.

Heatmap (heatmap.html): 24-column grayscale heatmap for today’s motion + tiny legend image.

Access (access.html): hotspot plan and security notes + monochrome illustration.