var PLAY_ICON  = '<svg class="ctp-i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.53.85l10-6.5a1 1 0 0 0 0-1.7l-10-6.5A1 1 0 0 0 8 5.5z"/></svg>';
var PAUSE_ICON = '<svg class="ctp-i-pause" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="4.5" width="4.2" height="15" rx="1.4"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.4"/></svg>';

class ClickToPlay extends HTMLElement {
  connectedCallback() {
    if (this._ready) return;       // enhance only once
    this._ready = true;

    var link = this.querySelector("a");
    var img  = this.querySelector("img");
    if (!link || !img) {
      console.warn("<click-to-play> expects <a href=gif><img src=still></a>");
      return;
    }
    this._link = link;
    this._img = img;
    this._gif = link.getAttribute("href");          // the motion
    this._poster = img.getAttribute("src");         // the still
    this._minLoading = parseInt(this.getAttribute("min-loading") || "350", 10);
    this._setState("idle");

    // Overlay: play button + spinner (decorative; the <a> is the control).
    var ui = document.createElement("span");
    ui.className = "ctp-ui";
    ui.setAttribute("aria-hidden", "true");
    ui.innerHTML = '<span class="ctp-btn">' + PLAY_ICON + PAUSE_ICON + '</span><span class="ctp-spin"></span>';
    this.appendChild(ui);

    if (!link.getAttribute("aria-label")) link.setAttribute("aria-label", "Play animation");

    link.addEventListener("click", this._onClick.bind(this));
    // touchscreens have no hover, so reveal the control on touch and fade it back out
    this.addEventListener("touchstart", this._onTouch.bind(this), { passive: true });
  }

  _setState(s) { this.dataset.ctpState = s; }

  _onTouch() {
    var self = this;
    this.classList.add("ctp-touched");
    clearTimeout(this._touchTimer);
    this._touchTimer = setTimeout(function () { self.classList.remove("ctp-touched"); }, 1400);
  }

  _onClick(e) {
    e.preventDefault();                 // hold the navigation; enhance instead
    var s = this.dataset.ctpState;
    if (s === "loading") return;
    if (s === "playing") { this._reset(); return; }  // tap again → back to still
    this._play();
  }

  _play() {
    var self = this;
    this._setState("loading");
    var t0 = performance.now();
    var pre = new Image();             // preload off-screen so it starts at frame 1
    pre.onload = function () {
      var wait = Math.max(0, self._minLoading - (performance.now() - t0));
      setTimeout(function () {
        self._img.src = self._gif;     // swap still → GIF; playback begins
        self._link.setAttribute("aria-label", "Show still image");
        self._setState("playing");
        self.dispatchEvent(new CustomEvent("ctp:play", { bubbles: true }));
      }, wait);
    };
    pre.onerror = function () {
      self._setState("error");
      self._link.setAttribute("aria-label", "Animation failed to load");
    };
    pre.src = this._gif;
  }

  _reset() {
    this._img.src = this._poster;      // back to the still
    this._link.setAttribute("aria-label", "Play animation");
    this._setState("idle");
    this.dispatchEvent(new CustomEvent("ctp:reset", { bubbles: true }));
  }
}

if (!customElements.get("click-to-play")) {
  customElements.define("click-to-play", ClickToPlay);
}
