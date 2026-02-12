const { useEffect, useRef } = React;

function AIAmbientBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    let width = 0;
    let height = 0;
    let dpr = 1;
    let raf = null;

    const points = [];
    const blobs = [];
    const mouse = { x: 0, y: 0, active: false, lastMove: 0 };

    function rand(min, max) {
      return Math.random() * (max - min) + min;
    }

    function resize() {
      dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      width = window.innerWidth;
      height = window.innerHeight;

      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = width + "px";
      canvas.style.height = height + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      points.length = 0;
      blobs.length = 0;

      const count = Math.max(72, Math.floor((width * height) / 17000));
      for (let i = 0; i < count; i++) {
        points.push({
          x: rand(0, width),
          y: rand(0, height),
          vx: rand(-0.24, 0.24),
          vy: rand(-0.2, 0.2),
          r: rand(1.5, 3.4),
        });
      }

      for (let i = 0; i < 3; i++) {
        blobs.push({
          x: rand(width * 0.1, width * 0.9),
          y: rand(height * 0.1, height * 0.9),
          radius: rand(180, 300),
          vx: rand(-0.04, 0.04),
          vy: rand(-0.04, 0.04),
          color: i % 2 === 0 ? "46, 153, 255" : "115, 87, 255",
          alpha: rand(0.06, 0.11),
        });
      }
    }

    function inQuietZone(x, y) {
      // Keep center area calmer so form remains readable.
      return x > width * 0.27 && x < width * 0.73 && y > height * 0.14 && y < height * 0.82;
    }

    function onMove(e) {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
      mouse.active = true;
      mouse.lastMove = performance.now();
    }

    function onLeave() {
      mouse.active = false;
    }

    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseout", onLeave);
    resize();

    function draw(now) {
      const t = now * 0.001;
      if (now - mouse.lastMove > 1800) mouse.active = false;

      const bg = ctx.createLinearGradient(0, 0, width, height);
      bg.addColorStop(0, "#07142c");
      bg.addColorStop(0.55, "#0e2048");
      bg.addColorStop(1, "#1a1a4b");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, width, height);

      for (const b of blobs) {
        b.x += b.vx;
        b.y += b.vy;
        if (b.x < -120) b.x = width + 120;
        if (b.x > width + 120) b.x = -120;
        if (b.y < -120) b.y = height + 120;
        if (b.y > height + 120) b.y = -120;

        const g = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.radius);
        g.addColorStop(0, `rgba(${b.color}, ${b.alpha})`);
        g.addColorStop(1, `rgba(${b.color}, 0)`);
        ctx.fillStyle = g;
        ctx.fillRect(b.x - b.radius, b.y - b.radius, b.radius * 2, b.radius * 2);
      }

      const projected = [];
      for (let i = 0; i < points.length; i++) {
        const p = points[i];

        if (mouse.active) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < 42000) {
            const force = (1 - d2 / 42000) * 0.03;
            p.vx += dx * force * 0.05;
            p.vy += dy * force * 0.05;
          }
        }

        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;

        const speed = Math.hypot(p.vx, p.vy);
        const maxSpeed = mouse.active ? 2.4 : 1.2;
        if (speed > maxSpeed) {
          const ratio = maxSpeed / speed;
          p.vx *= ratio;
          p.vy *= ratio;
        }

        p.vx *= 0.992;
        p.vy *= 0.992;

        projected.push({ x: p.x, y: p.y, r: p.r });
      }

      for (let i = 0; i < projected.length; i++) {
        for (let j = i + 1; j < projected.length; j++) {
          const a = projected[i];
          const b = projected[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < 12500) {
            let alpha = (1 - d2 / 12500) * 0.13;
            if (inQuietZone((a.x + b.x) * 0.5, (a.y + b.y) * 0.5)) alpha *= 0.2;
            ctx.strokeStyle = `rgba(176, 230, 255, ${alpha})`;
            ctx.lineWidth = 0.7;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      for (const p of projected) {
        let alpha = 0.92;
        let r = p.r;
        if (inQuietZone(p.x, p.y)) {
          alpha = 0.38;
          r *= 0.8;
        }

        ctx.beginPath();
        ctx.fillStyle = `rgba(224, 248, 255, ${alpha})`;
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
      }

      // Subtle scanline band for motion, kept very low contrast.
      const bandY = ((Math.sin(t * 0.6) + 1) * 0.5) * height;
      const band = ctx.createLinearGradient(0, bandY - 80, 0, bandY + 80);
      band.addColorStop(0, "rgba(120, 199, 255, 0)");
      band.addColorStop(0.5, "rgba(120, 199, 255, 0.05)");
      band.addColorStop(1, "rgba(120, 199, 255, 0)");
      ctx.fillStyle = band;
      ctx.fillRect(0, bandY - 80, width, 160);

      raf = requestAnimationFrame(draw);
    }

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseout", onLeave);
    };
  }, []);

  return <canvas ref={canvasRef} style={{ width: "100%", height: "100%" }} />;
}

const mount = document.getElementById("react-widget");
if (mount) {
  const root = ReactDOM.createRoot(mount);
  root.render(React.createElement(AIAmbientBackground));
}



