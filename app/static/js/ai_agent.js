document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("ai-agent-root");
  if (!root) return;

  const cfg = {
    stateUrl: root.dataset.stateUrl,
    activityUrl: root.dataset.activityUrl,
    journalTodayUrl: root.dataset.journalTodayUrl,
    journalWeekUrl: root.dataset.journalWeekUrl,
    idleSrc: root.dataset.idleSrc,
    journalingSrc: root.dataset.journalingSrc,
  };

  const state = {
    agent_name: "小咪",
    enabled: true,
    scale: 1,
    facing: "right",
    position_x: 24,
    position_y: 24,
  };
  let mode = "idle";
  let idleTimer = 0;
  let saveTimer = 0;
  let lastInteractionReport = 0;
  let isGenerating = false;

  const shell = document.createElement("div");
  shell.className = "ai-agent-shell is-hidden";
  const reopen = document.createElement("button");
  reopen.className = "ai-agent-reopen is-hidden";
  reopen.type = "button";
  reopen.setAttribute("aria-label", "显示 AI Agent");
  reopen.innerHTML = `<i class="bi bi-stars"></i><span>猫娘</span>`;
  shell.innerHTML = `
    <button class="ai-agent-avatar" type="button" aria-label="AI Agent">
      <img class="ai-agent-image" alt="" draggable="false">
      <span class="ai-agent-label"></span>
    </button>
    <div class="ai-agent-menu" hidden>
      <div class="ai-agent-menu__title">AI Agent</div>
      <div class="ai-agent-menu__row">
        <label class="form-label ai-agent-menu__mini mb-1" for="ai-agent-name">名字</label>
        <div class="input-group input-group-sm">
          <input id="ai-agent-name" class="form-control" type="text" maxlength="64">
          <button class="btn btn-outline-secondary" type="button" data-agent-action="rename">
            <i class="bi bi-check-lg"></i>
          </button>
        </div>
      </div>
      <div class="ai-agent-menu__row">
        <label class="form-label ai-agent-menu__mini mb-1" for="ai-agent-scale">缩放</label>
        <input id="ai-agent-scale" class="form-range" type="range" min="0.5" max="1.6" step="0.05">
      </div>
      <div class="ai-agent-menu__row d-flex flex-wrap gap-2">
        <button class="btn btn-sm btn-outline-secondary" type="button" data-agent-action="face">
          <i class="bi bi-arrow-left-right"></i> 转向
        </button>
        <button class="btn btn-sm btn-outline-danger ms-auto" type="button" data-agent-action="close">
          <i class="bi bi-x-lg"></i> 关闭
        </button>
      </div>
      <div class="ai-agent-menu__row d-flex flex-wrap gap-2">
        <button class="btn btn-sm btn-primary" type="button" data-agent-journal="today">
          <i class="bi bi-journal-text"></i> 日志
        </button>
        <button class="btn btn-sm btn-outline-primary" type="button" data-agent-journal="week">
          <i class="bi bi-calendar-week"></i> 周札
        </button>
      </div>
      <div class="ai-agent-menu__row ai-agent-menu__output" data-agent-output hidden></div>
    </div>
  `;
  root.appendChild(shell);
  root.appendChild(reopen);

  const avatar = shell.querySelector(".ai-agent-avatar");
  const image = shell.querySelector(".ai-agent-image");
  const label = shell.querySelector(".ai-agent-label");
  const menu = shell.querySelector(".ai-agent-menu");
  const nameInput = shell.querySelector("#ai-agent-name");
  const scaleInput = shell.querySelector("#ai-agent-scale");
  const output = shell.querySelector("[data-agent-output]");

  function clamp(value, low, high) {
    return Math.min(Math.max(value, low), high);
  }

  function applyState(next) {
    Object.assign(state, next || {});
    const scale = clamp(Number(state.scale) || 1, 0.5, 1.6);
    const x = clamp(Number(state.position_x) || 24, 0, Math.max(0, window.innerWidth - 48));
    const y = clamp(Number(state.position_y) || 24, 0, Math.max(0, window.innerHeight - 48));
    state.scale = scale;
    state.position_x = x;
    state.position_y = y;

    shell.classList.toggle("is-hidden", !state.enabled);
    reopen.classList.toggle("is-hidden", !!state.enabled);
    shell.classList.toggle("is-facing-left", state.facing === "left");
    shell.style.setProperty("--ai-agent-scale", String(scale));
    shell.style.left = `${x}px`;
    shell.style.bottom = `${y}px`;
    label.textContent = state.agent_name || "小咪";
    nameInput.value = state.agent_name || "小咪";
    scaleInput.value = String(scale);
    image.src = mode === "journaling" ? cfg.journalingSrc : cfg.idleSrc;
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  function saveState(patch) {
    Object.assign(state, patch);
    applyState(state);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      try {
        const data = await postJson(cfg.stateUrl, patch);
        if (data.state) applyState(data.state);
      } catch (err) {
        showOutput(`保存失败：${err.message}`);
      }
    }, 180);
  }

  function setMode(nextMode) {
    mode = nextMode;
    image.src = nextMode === "journaling" ? cfg.journalingSrc : cfg.idleSrc;
    shell.dataset.mode = nextMode;
  }

  function bumpJournaling(source) {
    if (!state.enabled || shell.classList.contains("is-hidden")) return;
    setMode("journaling");
    clearTimeout(idleTimer);
    if (!isGenerating) {
      idleTimer = setTimeout(() => setMode("idle"), 2200);
    }

    const now = Date.now();
    if (now - lastInteractionReport > 15000) {
      lastInteractionReport = now;
      reportActivity("interaction_active", "用户输入活跃", {source});
    }
  }

  function reportActivity(eventType, labelText, metadata) {
    postJson(cfg.activityUrl, {
      event_type: eventType,
      label: labelText,
      metadata: metadata || {},
    }).catch(() => {});
  }

  function showOutput(text) {
    output.hidden = false;
    output.textContent = text;
  }

  async function generateJournal(period) {
    const url = period === "week" ? cfg.journalWeekUrl : cfg.journalTodayUrl;
    const labelText = period === "week" ? "正在生成周札..." : "正在生成日志...";
    isGenerating = true;
    setMode("journaling");
    showOutput(labelText);
    try {
      const data = await postJson(url, {});
      showOutput(data.content || "没有返回日志内容。");
    } catch (err) {
      showOutput(`生成失败：${err.message}`);
    } finally {
      isGenerating = false;
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => setMode("idle"), 2200);
    }
  }

  let drag = null;
  avatar.addEventListener("pointerdown", event => {
    if (event.button !== undefined && event.button !== 0) return;
    const rect = shell.getBoundingClientRect();
    drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: event.clientX - rect.left,
      offsetBottom: rect.bottom - event.clientY,
      width: rect.width,
      height: rect.height,
      moved: false,
    };
    avatar.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  avatar.addEventListener("pointermove", event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = Math.abs(event.clientX - drag.startX);
    const dy = Math.abs(event.clientY - drag.startY);
    if (dx + dy > 4) drag.moved = true;
    if (!drag.moved) return;

    const x = clamp(event.clientX - drag.offsetX, 0, Math.max(0, window.innerWidth - drag.width));
    const y = clamp(window.innerHeight - event.clientY - drag.offsetBottom, 0, Math.max(0, window.innerHeight - drag.height));
    state.position_x = Math.round(x);
    state.position_y = Math.round(y);
    applyState(state);
  });

  avatar.addEventListener("pointerup", event => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const moved = drag.moved;
    avatar.releasePointerCapture(event.pointerId);
    drag = null;
    if (moved) {
      saveState({position_x: state.position_x, position_y: state.position_y});
    } else {
      menu.hidden = !menu.hidden;
    }
  });

  shell.addEventListener("click", event => {
    const action = event.target.closest("[data-agent-action]");
    if (action) {
      const kind = action.dataset.agentAction;
      if (kind === "rename") {
        saveState({agent_name: nameInput.value.trim() || "小咪"});
      } else if (kind === "face") {
        saveState({facing: state.facing === "left" ? "right" : "left"});
      } else if (kind === "close") {
        menu.hidden = true;
        saveState({enabled: false});
      }
      return;
    }

    const journal = event.target.closest("[data-agent-journal]");
    if (journal) {
      generateJournal(journal.dataset.agentJournal);
    }
  });

  scaleInput.addEventListener("input", () => {
    saveState({scale: Number(scaleInput.value)});
  });

  document.addEventListener("pointerdown", event => {
    bumpJournaling(event.target.closest("#ai-agent-root") ? "agent" : "mouse");
  }, true);

  document.addEventListener("keydown", () => {
    bumpJournaling("keyboard");
  }, true);

  document.addEventListener("click", event => {
    if (!event.target.closest("#ai-agent-root")) {
      menu.hidden = true;
    }
  });

  reopen.addEventListener("click", () => {
    saveState({enabled: true});
    menu.hidden = false;
  });

  window.addEventListener("resize", () => {
    applyState(state);
    saveState({position_x: state.position_x, position_y: state.position_y});
  });

  fetch(cfg.stateUrl)
    .then(response => response.json())
    .then(data => {
      if (data && data.state) {
        applyState(data.state);
        reportActivity("page_view", document.title || location.pathname, {
          path: location.pathname,
          query: location.search,
        });
      }
    })
    .catch(() => {
      shell.classList.add("is-hidden");
    });
});
