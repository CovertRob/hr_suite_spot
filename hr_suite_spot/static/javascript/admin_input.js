
  (() => {
    /* ---------- globals ---------- */
    const tzSel = document.getElementById('tz-select');
    const tzNow = document.getElementById('tz-now');
    const tbody = document.getElementById('tbody');
    let tz = moment.tz.guess();

    /* ---------- populate TZ dropdown ---------- */
    moment.tz.names().forEach(n => {
      const o = document.createElement('option');
      o.value = o.textContent = n;
      if (n === tz) o.selected = true;
      tzSel.appendChild(o);
    });
    tzSel.addEventListener('change', e => {
      tz = e.target.value;
      render();
    });

    const fmt = () =>
      (tzNow.textContent = `Now: ${moment().tz(tz).format('YYYY-MM-DD HH:mm z')}`);
    fmt();
    setInterval(fmt, 60000); // update every minute

    /* ---------- flatpickr (bug‑fixed) ---------- */
    flatpickr('#start, #end, #del-start, #del-end', {
        enableTime: true,
        dateFormat: 'Y-m-d H:i'
      });      

    /* ---------- helpers ---------- */
    const toUTC = loc => moment.tz(loc, 'YYYY-MM-DD HH:mm', tz).utc().format();
    const fromUTC = u => moment.utc(u).tz(tz).format('YYYY-MM-DD HH:mm');

    /* ---------- API wrappers ---------- */
    const api = {
      async list() {
        const r = await fetch('/admin/availability', { credentials: 'include' });
        if (!r.ok) throw new Error('list');
        return r.json();
      },
      async add(slots) {
        await fetch('/admin/availability', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slots, tz })
        });
      },
      async del(ids) {
        await fetch('/admin/availability', {
          method: 'DELETE',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids })
        });
      },
      async delRange(a, b) {
        await fetch('/admin/availability', {
          method: 'DELETE',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ range: { start: a, end: b } })
        });
      },
      async clear() {
        await fetch('/admin/availability', {
            method:'DELETE',
            credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ all:true })
        });
        }
    };

    /* ---------- render ---------- */
    async function render() {
      tbody.innerHTML = '';
      const rows = await api.list();
      rows
        .sort((a, b) => new Date(a.start) - new Date(b.start))
        .forEach(r => {
          const tr = document.createElement('tr');
          const [d, t] = fromUTC(r.start).split(' ');
          const utcDisplay =
            moment.utc(r.start).format('YYYY-MM-DD HH:mm') + ' UTC';
        tr.innerHTML = `
            <td>${d}</td>
            <td>${t}</td>
            <td>${utcDisplay}</td>
            <td><button class="danger" data-id="${r.id}">✕</button></td>
          `;
          tbody.appendChild(tr);
        });
    }

    /* ---------- add form ---------- */
    const addForm = document.getElementById('add-form');
    const recurring = document.getElementById('recurring');
    const freqWrap = document.getElementById('freq-wrap');
    const freq = document.getElementById('freq');
    const repeatWrap = document.getElementById('repeat-wrap');

    recurring.addEventListener('change', () => {
      const show = recurring.checked;
      freqWrap.style.display   = show ? 'inline-flex' : 'none';
      repeatWrap.style.display = show ? 'inline-flex' : 'none';
    });

    document.getElementById('clear-all')
    .addEventListener('click', async () => {
    if (!confirm('Delete ALL availability? This cannot be undone.')) return;
    await api.clear();
    render();
    });

    

    addForm.addEventListener('submit', async ev => {
      ev.preventDefault();
      const s = document.getElementById('start').value;
      const en = document.getElementById('end').value;
      if (!s) return alert('Start required');

      let slots = [];
      const sUTC = toUTC(s);

      if (!en) {
        slots.push({
          start: sUTC,
          end:   moment.utc(sUTC).add(30, 'm').toISOString()
        });
    } else {
        const eUTC      = toUTC(en);          // convert "To" to UTC ISO
        const endMoment = moment.utc(eUTC);   // cache once
        let   cur       = moment.utc(sUTC);   // start moment
      
        while (cur < endMoment) {             // strictly <  (exclusive)
          const next = cur.clone().add(30, 'm');
      
          slots.push({
            start: cur.toISOString(),
            end:   next.toISOString()
          });
      
          cur = next;                         // advance 30 min
        }
      }      
      
      if (recurring.checked) {
        const base = [...slots];
        const repeats = Number(document.getElementById('repeat-count').value);
        for (let i = 1; i <= repeats; i++) {
          base.forEach(o => {
            const s = moment.utc(o.start);
            const e = moment.utc(o.end);
            if (freq.value === 'weekly') {
              s.add(i, 'w');
              e.add(i, 'w');
            } else if (freq.value === 'daily') {
              s.add(i, 'd');
              e.add(i, 'd');
            } else if (freq.value === 'weekdays') {
              let d = s.clone().add(i, 'd');
              if ([6, 0].includes(d.day())) return; // skip weekends
              s.add(i, 'd');
              e.add(i, 'd');
            }
            slots.push({
              start: s.toISOString(),
              end: e.toISOString()
            });
          });
        }
      }

      await api.add(slots);
      addForm.reset();
      freqWrap.style.display = 'none';
      render();
    });

    /* ---------- delete ---------- */
    tbody.addEventListener('click', async e => {
      if (e.target.matches('button[data-id]')) {
        await api.del([e.target.dataset.id]);
        render();
      }
    });

    document.getElementById('del-range').addEventListener('submit', async e => {
      e.preventDefault();
      const a = document.getElementById('del-start').value;
      const b = document.getElementById('del-end').value;
      if (!a || !b) return alert('Pick both');
      await api.delRange(toUTC(a), toUTC(b));
      e.target.reset();
      render();
    });

    render();
  })();
