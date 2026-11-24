/* Native Built-in Interactive Diagram Editor — Hand-Drawn Sketch Style (Excalidraw-inspired, Draw.io XML compatible) */

const NDE_SKETCH_FONT = '"Virgil", "Patrick Hand", "Architects Daughter", "Segoe Print", cursive';

class NativeDiagramEditor {
  constructor(containerEl, opts = {}) {
    this.container = containerEl;
    this.onSave = opts.onSave || (async () => {});
    this.onClose = opts.onClose || null;
    this.nodes = [];
    this.edges = [];
    this.selected = null; // { type: 'node'|'edge', id }
    this.connectMode = false;
    this.connectSourceId = null;
    this.sketchStyle = true;
    this.dragNode = null;
    this.dragOffset = { x: 0, y: 0 };
    this.pan = { x: 28, y: 28, scale: 1 };
    this.panning = false;
    this.panStart = { x: 0, y: 0 };
    this.history = [];
    this.diagramName = 'Architecture Diagram';
    this.dirty = false;
    this._buildUI();
  }

  _buildUI() {
    this.container.innerHTML = `
      <div class="nde-shell">
        <div class="nde-toolbar">
          <div class="nde-group">
            <button class="nde-btn" data-add="step" title="Add Process Box (Warm Cream)">+ Box</button>
            <button class="nde-btn" data-add="oval" title="Add Loop / State Oval (Soft Blush)">+ Oval</button>
            <button class="nde-btn" data-add="decision" title="Add Decision Diamond">+ Decision</button>
            <button class="nde-btn" data-add="system" title="Add Memory / Store (Sky Blue)">+ Store</button>
            <button class="nde-btn" data-add="policy" title="Add Policy / Guard (Lavender)">+ Policy</button>
            <button class="nde-btn" data-add="container" title="Add Outer Session / Boundary Frame">+ Frame</button>
          </div>
          <span class="nde-sep"></span>
          <div class="nde-group">
            <button class="nde-btn" id="nde-connect-btn" title="Click source shape, then target shape to draw arrow">↗ Connect</button>
            <button class="nde-btn" id="nde-layout-btn" title="Clean layered auto-layout">⊞ Layout</button>
            <button class="nde-btn active" id="nde-sketch-btn" title="Toggle hand-drawn sketch look">✎ Sketch</button>
            <button class="nde-btn" id="nde-undo-btn" title="Undo">↶</button>
            <button class="nde-btn nde-danger" id="nde-del-btn" title="Delete selected">🗑</button>
          </div>
          <span class="nde-sep"></span>
          <div class="nde-group nde-colors" title="Pastel fill for selected shape">
            <button class="nde-swatch" data-fill="#fef9d7" data-stroke="#1e1e1e" style="background:#fef9d7;border-color:#1e1e1e" title="Warm Cream"></button>
            <button class="nde-swatch" data-fill="#eaf4fe" data-stroke="#1e1e1e" style="background:#eaf4fe;border-color:#1e1e1e" title="Sky Blue"></button>
            <button class="nde-swatch" data-fill="#f0edfe" data-stroke="#1e1e1e" style="background:#f0edfe;border-color:#1e1e1e" title="Soft Lavender"></button>
            <button class="nde-swatch" data-fill="#fef0f2" data-stroke="#1e1e1e" style="background:#fef0f2;border-color:#1e1e1e" title="Soft Blush"></button>
            <button class="nde-swatch" data-fill="#e8f8ee" data-stroke="#1e1e1e" style="background:#e8f8ee;border-color:#1e1e1e" title="Mint"></button>
            <button class="nde-swatch" data-fill="#ffffff" data-stroke="#1e1e1e" style="background:#ffffff;border-color:#1e1e1e" title="White Frame"></button>
          </div>
          <span class="nde-sep"></span>
          <div class="nde-group">
            <button class="nde-btn" id="nde-zin">＋</button>
            <button class="nde-btn" id="nde-zout">－</button>
            <button class="nde-btn" id="nde-zfit">Fit</button>
          </div>
          <div class="spacer"></div>
          <span id="nde-status" class="muted" style="font-size:11.5px;">Double-click to edit (use | for subtitle) · Drag to move</span>
          <button class="btn btn-primary btn-xs" id="nde-save-btn">💾 Save into Document</button>
          ${this.onClose ? '<button class="btn btn-secondary btn-xs" id="nde-close-btn">← Back to Document</button>' : ''}
        </div>
        <div class="nde-canvas-wrap nde-paper-bg" id="nde-wrap">
          <svg class="nde-svg" id="nde-svg" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <filter id="nde-rough" x="-5%" y="-5%" width="110%" height="110%">
                <feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="2" result="noise" seed="3"/>
                <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.4" xChannelSelector="R" yChannelSelector="G"/>
              </filter>
              <marker id="nde-arrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                <path d="M 2 2 L 10 6 L 2 10" fill="none" stroke="#1e1e1e" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
              </marker>
              <marker id="nde-arrow-sel" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                <path d="M 2 2 L 10 6 L 2 10" fill="none" stroke="#EB0A1E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </marker>
            </defs>
            <g id="nde-viewport"></g>
          </svg>
        </div>
      </div>
    `;

    this.svg = this.container.querySelector('#nde-svg');
    this.vp = this.container.querySelector('#nde-viewport');
    this.wrap = this.container.querySelector('#nde-wrap');
    this.statusEl = this.container.querySelector('#nde-status');

    this.container.querySelectorAll('[data-add]').forEach((b) => {
      b.onclick = () => this.addNode(b.dataset.add);
    });
    this.container.querySelector('#nde-connect-btn').onclick = () => this.toggleConnectMode();
    this.container.querySelector('#nde-layout-btn').onclick = () => this.autoLayout();
    this.container.querySelector('#nde-sketch-btn').onclick = (e) => {
      this.sketchStyle = !this.sketchStyle;
      e.currentTarget.classList.toggle('active', this.sketchStyle);
      this.render();
    };
    this.container.querySelector('#nde-undo-btn').onclick = () => this.undo();
    this.container.querySelector('#nde-del-btn').onclick = () => this.deleteSelected();
    this.container.querySelector('#nde-zin').onclick = () => this.zoomBy(1.2);
    this.container.querySelector('#nde-zout').onclick = () => this.zoomBy(0.83);
    this.container.querySelector('#nde-zfit').onclick = () => this.fit();
    this.container.querySelector('#nde-save-btn').onclick = () => this.saveNow();
    const closeBtn = this.container.querySelector('#nde-close-btn');
    if (closeBtn) closeBtn.onclick = () => this.onClose && this.onClose();

    this.container.querySelectorAll('.nde-swatch').forEach((s) => {
      s.onclick = () => {
        if (!this.selected || this.selected.type !== 'node') return;
        const n = this.nodes.find((x) => x.id === this.selected.id);
        if (!n) return;
        this._pushHistory();
        n.fill = s.dataset.fill;
        n.stroke = s.dataset.stroke;
        this.dirty = true;
        this.render();
      };
    });

    this._bindCanvasEvents();
  }

  _bindCanvasEvents() {
    this.svg.addEventListener('mousedown', (e) => {
      if (e.target === this.svg) {
        this.selected = null;
        this.connectSourceId = null;
        this.panning = true;
        this.panStart = { x: e.clientX - this.pan.x, y: e.clientY - this.pan.y };
        this.render();
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (this.dragNode) {
        const pt = this._clientToWorld(e.clientX, e.clientY);
        this.dragNode.x = Math.round((pt.x - this.dragOffset.x) / 10) * 10;
        this.dragNode.y = Math.round((pt.y - this.dragOffset.y) / 10) * 10;
        this.dirty = true;
        this.render();
      } else if (this.panning) {
        this.pan.x = e.clientX - this.panStart.x;
        this.pan.y = e.clientY - this.panStart.y;
        this._applyTransform();
      }
    });

    window.addEventListener('mouseup', () => {
      this.dragNode = null;
      this.panning = false;
    });

    this.svg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.91;
      this.zoomBy(factor, e.clientX, e.clientY);
    }, { passive: false });

    this.wrap.tabIndex = 0;
    this.wrap.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.onClose) {
        e.preventDefault();
        this.onClose();
        return;
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && this.selected) {
        e.preventDefault();
        this.deleteSelected();
      }
    });
  }

  _clientToWorld(cx, cy) {
    const r = this.svg.getBoundingClientRect();
    return {
      x: (cx - r.left - this.pan.x) / this.pan.scale,
      y: (cy - r.top - this.pan.y) / this.pan.scale,
    };
  }

  _applyTransform() {
    this.vp.setAttribute('transform', `translate(${this.pan.x},${this.pan.y}) scale(${this.pan.scale})`);
  }

  zoomBy(factor, clientX = null, clientY = null) {
    const r = this.svg.getBoundingClientRect();
    const mx = clientX !== null ? clientX - r.left : r.width / 2;
    const my = clientY !== null ? clientY - r.top : r.height / 2;
    const next = Math.min(2.4, Math.max(0.3, this.pan.scale * factor));
    const ratio = next / this.pan.scale;
    this.pan.x = mx - (mx - this.pan.x) * ratio;
    this.pan.y = my - (my - this.pan.y) * ratio;
    this.pan.scale = next;
    this._applyTransform();
  }

  fit() {
    if (!this.nodes.length) return;
    const r = this.svg.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const minX = Math.min(...this.nodes.map((n) => n.x));
    const minY = Math.min(...this.nodes.map((n) => n.y));
    const maxX = Math.max(...this.nodes.map((n) => n.x + n.w));
    const maxY = Math.max(...this.nodes.map((n) => n.y + n.h));
    const bw = Math.max(220, maxX - minX + 90);
    const bh = Math.max(160, maxY - minY + 90);
    const s = Math.min(1.15, Math.max(0.35, Math.min(r.width / bw, r.height / bh)));
    this.pan.scale = s;
    this.pan.x = (r.width - (maxX - minX) * s) / 2 - minX * s;
    this.pan.y = (r.height - (maxY - minY) * s) / 2 - minY * s;
    this._applyTransform();
  }

  _pushHistory() {
    this.history.push(JSON.stringify({ nodes: this.nodes, edges: this.edges }));
    if (this.history.length > 30) this.history.shift();
  }

  undo() {
    if (!this.history.length) return;
    const snap = JSON.parse(this.history.pop());
    this.nodes = snap.nodes;
    this.edges = snap.edges;
    this.selected = null;
    this.render();
  }

  toggleConnectMode() {
    this.connectMode = !this.connectMode;
    this.connectSourceId = null;
    const btn = this.container.querySelector('#nde-connect-btn');
    btn.classList.toggle('active', this.connectMode);
    this.statusEl.textContent = this.connectMode
      ? 'Connect Mode: Click source shape, then click target shape'
      : 'Double-click to edit (use | for subtitle) · Drag to move';
  }

  _normalizePastel(fill) {
    const legacyMap = {
      '#dae8fc': '#eaf4fe',
      '#d5e8d4': '#e8f8ee',
      '#fff2cc': '#fef9d7',
      '#e1d5e7': '#f0edfe',
      '#f8cecc': '#fef0f2',
    };
    return legacyMap[(fill || '').toLowerCase()] || fill || '#fef9d7';
  }

  loadDrawioXml(xml, name = 'Architecture Diagram') {
    this.diagramName = name;
    this.nodes = [];
    this.edges = [];
    this.history = [];
    this.selected = null;
    this.dirty = false;

    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(xml || '', 'text/xml');
      const cells = Array.from(doc.querySelectorAll('mxCell'));
      for (const c of cells) {
        const id = c.getAttribute('id');
        if (id === '0' || id === '1') continue;
        const style = c.getAttribute('style') || '';
        const value = (c.getAttribute('value') || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        const rawFill = (style.match(/fillColor=([^;]+)/) || [])[1] || '#fef9d7';
        const fill = this._normalizePastel(rawFill);
        const shape = style.includes('rhombus')
          ? 'decision'
          : style.includes('ellipse')
            ? 'oval'
            : style.includes('container=1')
              ? 'container'
              : 'rect';

        if (c.getAttribute('vertex') === '1') {
          const geo = c.querySelector('mxGeometry');
          this.nodes.push({
            id,
            label: value || id,
            x: parseFloat(geo?.getAttribute('x') || '60'),
            y: parseFloat(geo?.getAttribute('y') || '60'),
            w: parseFloat(geo?.getAttribute('width') || '210'),
            h: parseFloat(geo?.getAttribute('height') || '68'),
            fill,
            stroke: '#1e1e1e',
            shape,
          });
        } else if (c.getAttribute('edge') === '1') {
          const src = c.getAttribute('source');
          const dst = c.getAttribute('target');
          if (src && dst) {
            this.edges.push({ id, source: src, target: dst, label: value });
          }
        }
      }
    } catch (_) {}

    if (!this.nodes.length) {
      this.nodes.push({ id: '2', label: name, x: 80, y: 80, w: 220, h: 70, fill: '#fef9d7', stroke: '#1e1e1e', shape: 'rect' });
    }
    this.render();
    setTimeout(() => this.fit(), 30);
  }

  addNode(preset) {
    this._pushHistory();
    const presets = {
      step: { label: 'Event inbox | one row per event', fill: '#fef9d7', stroke: '#1e1e1e', shape: 'rect', w: 210, h: 72 },
      oval: { label: 'Core loop | execute + verify', fill: '#fef0f2', stroke: '#1e1e1e', shape: 'oval', w: 210, h: 90 },
      decision: { label: 'Eligible?', fill: '#fef9d7', stroke: '#1e1e1e', shape: 'decision', w: 155, h: 90 },
      system: { label: 'State Store | notes · history', fill: '#eaf4fe', stroke: '#1e1e1e', shape: 'rect', w: 220, h: 70 },
      policy: { label: 'Permissions | allow or ask', fill: '#f0edfe', stroke: '#1e1e1e', shape: 'rect', w: 220, h: 70 },
      container: { label: 'A run | one wake-up session', fill: '#ffffff', stroke: '#1e1e1e', shape: 'container', w: 320, h: 240 },
    };
    const p = presets[preset] || presets.step;
    const maxId = Math.max(1, ...this.nodes.map((n) => parseInt(n.id, 10) || 1), ...this.edges.map((e) => parseInt(e.id, 10) || 1));
    const id = String(maxId + 1);
    const offset = (this.nodes.length % 5) * 30;
    const node = { id, x: 90 + offset, y: 90 + offset, ...p };
    if (preset === 'container') this.nodes.unshift(node);
    else this.nodes.push(node);
    this.selected = { type: 'node', id };
    this.dirty = true;
    this.render();
  }

  deleteSelected() {
    if (!this.selected) return;
    this._pushHistory();
    if (this.selected.type === 'node') {
      const id = this.selected.id;
      this.nodes = this.nodes.filter((n) => n.id !== id);
      this.edges = this.edges.filter((e) => e.source !== id && e.target !== id);
    } else {
      this.edges = this.edges.filter((e) => e.id !== this.selected.id);
    }
    this.selected = null;
    this.dirty = true;
    this.render();
  }

  autoLayout() {
    if (!this.nodes.length) return;
    this._pushHistory();
    const indeg = Object.fromEntries(this.nodes.map((n) => [n.id, 0]));
    const adj = Object.fromEntries(this.nodes.map((n) => [n.id, []]));
    for (const e of this.edges) {
      if (adj[e.source] && e.target in indeg) {
        adj[e.source].push(e.target);
        indeg[e.target]++;
      }
    }
    const levels = {};
    const q = this.nodes.filter((n) => indeg[n.id] === 0).map((n) => n.id);
    if (!q.length) q.push(this.nodes[0].id);
    q.forEach((id) => (levels[id] = 0));
    for (let i = 0; i < q.length; i++) {
      const cur = q[i];
      for (const nxt of adj[cur] || []) {
        if (!(nxt in levels)) {
          levels[nxt] = levels[cur] + 1;
          q.push(nxt);
        }
      }
    }
    this.nodes.forEach((n) => { if (!(n.id in levels)) levels[n.id] = 0; });
    const rows = {};
    for (const n of this.nodes) {
      (rows[levels[n.id]] = rows[levels[n.id]] || []).push(n);
    }
    Object.keys(rows).sort((a, b) => Number(a) - Number(b)).forEach((lvl) => {
      rows[lvl].forEach((n, ci) => {
        n.x = 60 + ci * 270;
        n.y = 60 + Number(lvl) * 140;
      });
    });
    this.dirty = true;
    this.render();
    this.fit();
  }

  _escapeXml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  toDrawioXml() {
    const cells = [];
    for (const n of this.nodes) {
      const shapeStyle =
        n.shape === 'decision' ? 'rhombus;'
          : n.shape === 'oval' ? 'ellipse;'
            : n.shape === 'container' ? 'rounded=1;container=1;'
              : 'rounded=1;';
      const style = `${shapeStyle}whiteSpace=wrap;html=1;fillColor=${n.fill};strokeColor=#1e1e1e;strokeWidth=2;fontFamily=Architects Daughter;fontSize=14;`;
      cells.push(
        `<mxCell id="${this._escapeXml(n.id)}" value="${this._escapeXml(n.label)}" style="${style}" vertex="1" parent="1">` +
        `<mxGeometry x="${Math.round(n.x)}" y="${Math.round(n.y)}" width="${Math.round(n.w)}" height="${Math.round(n.h)}" as="geometry"/></mxCell>`
      );
    }
    for (const e of this.edges) {
      const style = 'edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#1e1e1e;strokeWidth=1.8;endArrow=open;fontFamily=Architects Daughter;fontSize=12;';
      cells.push(
        `<mxCell id="${this._escapeXml(e.id)}" value="${this._escapeXml(e.label)}" style="${style}" edge="1" parent="1" source="${this._escapeXml(e.source)}" target="${this._escapeXml(e.target)}">` +
        `<mxGeometry relative="1" as="geometry"/></mxCell>`
      );
    }
    return (
      '<?xml version="1.0" encoding="UTF-8"?>\n' +
      '<mxfile host="specit" agent="SPECiTSketch" version="24.0.0">\n' +
      `  <diagram id="diag-1" name="${this._escapeXml(this.diagramName)}">\n` +
      '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827">\n' +
      '      <root>\n' +
      '        <mxCell id="0"/>\n' +
      '        <mxCell id="1" parent="0"/>\n' +
      `        ${cells.join('\n        ')}\n` +
      '      </root>\n' +
      '    </mxGraphModel>\n' +
      '  </diagram>\n' +
      '</mxfile>'
    );
  }

  toCleanSvg() {
    if (!this.nodes.length) return '';
    const pad = 42;
    const hasSelfLoop = this.edges.some((e) => e.source === e.target);
    const minX = Math.min(...this.nodes.map((n) => n.x)) - pad;
    const minY = Math.min(...this.nodes.map((n) => n.y)) - pad;
    const maxX = Math.max(...this.nodes.map((n) => n.x + n.w)) + pad + (hasSelfLoop ? 150 : 0);
    const maxY = Math.max(...this.nodes.map((n) => n.y + n.h)) + pad;
    const w = Math.max(260, maxX - minX);
    const h = Math.max(160, maxY - minY);
    const uid = `doc_${Math.random().toString(36).slice(2, 8)}`;
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${minX} ${minY} ${w} ${h}" width="${Math.min(960, w)}" style="max-width:100%;height:auto;background:#ffffff;font-family:${NDE_SKETCH_FONT};">` +
      '<defs>' +
      `<filter id="${uid}_rough" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="2" result="noise" seed="3"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="1.3" xChannelSelector="R" yChannelSelector="G"/></filter>` +
      `<marker id="${uid}_arrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M 2 2 L 10 6 L 2 10" fill="none" stroke="#1e1e1e" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></marker>` +
      '</defs>' +
      `${this._renderNodesMarkup(false, `${uid}_rough`)}${this._renderEdgesMarkup(`${uid}_arrow`, false, `${uid}_rough`)}</svg>`
    );
  }

  static renderXmlToSvg(xml, name = 'Diagram', sketchStyle = true) {
    const tmp = document.createElement('div');
    const inst = new NativeDiagramEditor(tmp);
    inst.sketchStyle = sketchStyle;
    inst.loadDrawioXml(xml, name);
    // Keep containers behind nodes
    const containers = inst.nodes.filter((n) => n.shape === 'container');
    const regular = inst.nodes.filter((n) => n.shape !== 'container');
    inst.nodes = [...containers, ...regular];
    return inst.toCleanSvg();
  }

  async saveNow() {
    const xml = this.toDrawioXml();
    const svg = this.toCleanSvg();
    await this.onSave(xml, svg);
    this.dirty = false;
  }

  _wrapLines(text, maxChars = 24) {
    const words = String(text || '').split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
      if ((cur + ' ' + w).trim().length > maxChars && cur) {
        lines.push(cur);
        cur = w;
      } else {
        cur = (cur + ' ' + w).trim();
      }
    }
    if (cur) lines.push(cur);
    return lines.slice(0, 3);
  }

  _edgePath(src, dst, parallelOffset = 0) {
    // Clean external right-side loop for self-transitions (e.g. CLEP -> CLEP) so label NEVER overlaps box text!
    if (src.id === dst.id) {
      const rx = src.x + src.w + 2;
      const y1 = src.y + Math.min(20, src.h * 0.28);
      const y2 = src.y + src.h - Math.min(20, src.h * 0.28);
      const cy = src.y + src.h / 2;
      const loopW = 115;
      return {
        d: `M ${rx} ${y1} C ${rx + loopW} ${y1 - 28}, ${rx + loopW} ${y2 + 28}, ${rx + 2} ${y2}`,
        lx: rx + loopW + 6,
        ly: cy - 4,
      };
    }

    const sx = src.x + src.w / 2;
    const sy = src.y + src.h / 2;
    const dx = dst.x + dst.w / 2;
    const dy = dst.y + dst.h / 2;
    const vGap = dy > sy ? dst.y - (src.y + src.h) : src.y - (dst.y + dst.h);
    const hGap = dx > sx ? dst.x - (src.x + src.w) : src.x - (dst.x + dst.w);

    // Prefer vertical top/bottom ports whenever nodes sit on separate rows (prevents slicing across sibling boxes)
    const useVertical = vGap >= 24 && (hGap < 40 || Math.abs(dy - sy) >= Math.abs(dx - sx) * 0.45);

    if (useVertical) {
      const goingDown = dy >= sy;
      const x1 = sx + parallelOffset;
      const y1 = goingDown ? src.y + src.h + 2 : src.y - 2;
      const x2 = dx + parallelOffset;
      const y2 = goingDown ? dst.y - 4 : dst.y + dst.h + 4;
      const midY = (y1 + y2) / 2;
      const lx = (x1 + x2) / 2 + (parallelOffset ? Math.sign(parallelOffset) * 18 : 0);
      const ly = midY + (parallelOffset ? Math.sign(parallelOffset) * 6 : 0);
      return { d: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`, lx, ly };
    } else {
      const goingRight = dx >= sx;
      const x1 = goingRight ? src.x + src.w + 2 : src.x - 2;
      const y1 = sy + parallelOffset;
      const x2 = goingRight ? dst.x - 4 : dst.x + dst.w + 4;
      const y2 = dy + parallelOffset;
      const midX = (x1 + x2) / 2;
      const lx = midX;
      const ly = (y1 + y2) / 2 + (parallelOffset > 0 ? 14 : parallelOffset < 0 ? -14 : -12);
      return { d: `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`, lx, ly };
    }
  }

  _computeEdgeOffsets() {
    // Spread bidirectional (A->B and B->A) or parallel edges so arrows and labels NEVER overlap
    const groups = new Map();
    for (const e of this.edges) {
      if (e.source === e.target) continue;
      const key = e.source < e.target ? `${e.source}::${e.target}` : `${e.target}::${e.source}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(e);
    }
    const offsets = {};
    for (const list of groups.values()) {
      if (list.length === 1) {
        offsets[list[0].id] = 0;
      } else {
        const spread = 20;
        const start = -((list.length - 1) * spread) / 2;
        list.forEach((e, idx) => {
          offsets[e.id] = start + idx * spread;
        });
      }
    }
    return offsets;
  }

  _renderEdgesMarkup(markerId, interactive = true) {
    const byId = Object.fromEntries(this.nodes.map((n) => [n.id, n]));
    const offsets = this._computeEdgeOffsets();
    // NOTE: Never apply objectBoundingBox SVG filters to 1D straight <path> edges (zero-height bbox clips straight lines invisible!)
    return this.edges.map((e) => {
      const s = byId[e.source];
      const t = byId[e.target];
      if (!s || !t) return '';
      const isSel = interactive && this.selected && this.selected.type === 'edge' && this.selected.id === e.id;
      const { d, lx, ly } = this._edgePath(s, t, offsets[e.id] || 0);
      const stroke = isSel ? '#EB0A1E' : '#1e1e1e';
      const mk = isSel ? 'nde-arrow-sel' : markerId;
      const labelLines = e.label ? this._wrapLines(e.label, 22) : [];
      let labelHtml = '';
      if (labelLines.length) {
        const maxChars = Math.max(...labelLines.map((l) => l.length));
        const boxW = Math.max(44, maxChars * 7.4 + 12);
        const boxH = labelLines.length * 16 + 6;
        const topY = ly - boxH / 2;
        labelHtml =
          `<rect x="${lx - boxW / 2}" y="${topY}" width="${boxW}" height="${boxH}" rx="5" fill="#ffffff" fill-opacity="0.92"/>` +
          labelLines.map((ln, idx) =>
            `<text x="${lx}" y="${topY + 14 + idx * 16}" text-anchor="middle" font-family="${this._escapeXml(NDE_SKETCH_FONT)}" font-size="13.5" fill="#1e1e1e">${this._escapeXml(ln)}</text>`
          ).join('');
      }
      return `<g class="nde-edge" data-edge-id="${this._escapeXml(e.id)}" style="cursor:pointer;">
        <path d="${d}" fill="none" stroke="transparent" stroke-width="14"/>
        <path d="${d}" fill="none" stroke="${stroke}" stroke-width="${isSel ? 2.5 : 1.85}" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#${mk})"/>
        ${labelHtml}
      </g>`;
    }).join('');
  }

  _renderNodesMarkup(interactive = true, filterId = 'nde-rough') {
    const filt = this.sketchStyle ? ` filter="url(#${filterId})"` : '';
    return this.nodes.map((n) => {
      const isSel = interactive && this.selected && this.selected.type === 'node' && this.selected.id === n.id;
      const isConnSrc = interactive && this.connectSourceId === n.id;
      const stroke = isSel || isConnSrc ? '#EB0A1E' : '#1e1e1e';
      const sw = isSel || isConnSrc ? 2.6 : 1.85;
      let shapeSvg;
      if (n.shape === 'decision') {
        const mx = n.x + n.w / 2, my = n.y + n.h / 2;
        shapeSvg = `<polygon points="${mx},${n.y} ${n.x + n.w},${my} ${mx},${n.y + n.h} ${n.x},${my}" fill="${n.fill}" stroke="${stroke}" stroke-width="${sw}" stroke-linejoin="round"${filt}/>`;
      } else if (n.shape === 'oval' || n.shape === 'state') {
        shapeSvg = `<ellipse cx="${n.x + n.w / 2}" cy="${n.y + n.h / 2}" rx="${n.w / 2}" ry="${n.h / 2}" fill="${n.fill}" stroke="${stroke}" stroke-width="${sw}"${filt}/>`;
      } else {
        shapeSvg = `<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="16" ry="16" fill="${n.fill}" stroke="${stroke}" stroke-width="${sw}"${filt}/>`;
      }

      // Support "Title | subtitle" syntax like "Event inbox | one row per event"
      const parts = String(n.label || '').split('|').map((x) => x.trim()).filter(Boolean);
      const titleText = parts[0] || '';
      const subText = parts.slice(1).join(' · ');
      const titleLines = this._wrapLines(titleText, Math.max(16, Math.floor(n.w / 9)));
      const subLines = subText ? this._wrapLines(subText, Math.max(20, Math.floor(n.w / 7.5))) : [];

      let textSvg = '';
      if (n.shape === 'container') {
        textSvg += `<text x="${n.x + 18}" y="${n.y + 30}" text-anchor="start" font-family="${this._escapeXml(NDE_SKETCH_FONT)}" font-size="22" font-weight="600" fill="#1e1e1e" style="pointer-events:none;">${this._escapeXml(titleText)}</text>`;
        if (subText) {
          textSvg += `<text x="${n.x + 18}" y="${n.y + 50}" text-anchor="start" font-family="${this._escapeXml(NDE_SKETCH_FONT)}" font-size="14" fill="#374151" style="pointer-events:none;">${this._escapeXml(subText)}</text>`;
        }
      } else {
        const allLines = [
          ...titleLines.map((t) => ({ t, size: 17, weight: '600', fill: '#1e1e1e' })),
          ...subLines.map((t) => ({ t, size: 14, weight: '400', fill: '#334155' })),
        ];
        const lineH = 19;
        const startY = n.y + n.h / 2 - ((allLines.length - 1) * lineH) / 2 + 5;
        textSvg = allLines.map((item, i) =>
          `<text x="${n.x + n.w / 2}" y="${startY + i * lineH}" text-anchor="middle" font-family="${this._escapeXml(NDE_SKETCH_FONT)}" font-size="${item.size}" font-weight="${item.weight}" fill="${item.fill}" style="pointer-events:none;">${this._escapeXml(item.t)}</text>`
        ).join('');
      }
      return `<g class="nde-node" data-node-id="${this._escapeXml(n.id)}" style="cursor:move;">${shapeSvg}${textSvg}</g>`;
    }).join('');
  }

  render() {
    // Draw container frames first, then nodes, then edges on top
    const containers = this.nodes.filter((n) => n.shape === 'container');
    const regular = this.nodes.filter((n) => n.shape !== 'container');
    this.nodes = [...containers, ...regular];

    this.vp.innerHTML = this._renderNodesMarkup(true) + this._renderEdgesMarkup('nde-arrow', true);
    this._applyTransform();

    this.vp.querySelectorAll('.nde-node').forEach((g) => {
      const id = g.dataset.nodeId;
      const node = this.nodes.find((x) => x.id === id);
      g.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        if (this.connectMode) {
          if (!this.connectSourceId) {
            this.connectSourceId = id;
            this.statusEl.textContent = `Source "${node.label}" selected — now click target shape`;
            this.render();
          } else if (this.connectSourceId !== id) {
            this._pushHistory();
            const maxId = Math.max(1, ...this.nodes.map((n) => parseInt(n.id, 10) || 1), ...this.edges.map((ed) => parseInt(ed.id, 10) || 1));
            const lbl = window.prompt('Arrow label (optional):', '') || '';
            this.edges.push({ id: String(maxId + 1), source: this.connectSourceId, target: id, label: lbl.trim() });
            this.connectSourceId = null;
            this.dirty = true;
            this.toggleConnectMode();
            this.render();
          }
          return;
        }
        this.selected = { type: 'node', id };
        this._pushHistory();
        const pt = this._clientToWorld(e.clientX, e.clientY);
        this.dragNode = node;
        this.dragOffset = { x: pt.x - node.x, y: pt.y - node.y };
        this.render();
      });
      g.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        const next = window.prompt('Edit label (use | to add a subtitle line):', node.label);
        if (next !== null) {
          this._pushHistory();
          node.label = next.trim() || node.label;
          this.dirty = true;
          this.render();
        }
      });
    });

    this.vp.querySelectorAll('.nde-edge').forEach((g) => {
      const id = g.dataset.edgeId;
      const edge = this.edges.find((x) => x.id === id);
      g.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        this.selected = { type: 'edge', id };
        this.render();
      });
      g.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        const next = window.prompt('Edit arrow label:', edge.label || '');
        if (next !== null) {
          this._pushHistory();
          edge.label = next.trim();
          this.dirty = true;
          this.render();
        }
      });
    });
  }
}

window.NativeDiagramEditor = NativeDiagramEditor;
