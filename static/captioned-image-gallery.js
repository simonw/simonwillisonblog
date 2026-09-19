/**
 * <captioned-image-gallery> web component
 *
 * Lays out a list of <figure> children in justified rows: items in a row
 * share a common height, with widths proportional to each image's aspect
 * ratio. Handles mixed portrait / landscape mixes naturally.
 *
 * Clicking any image opens a full-screen lightbox with prev / next
 * navigation and PhotoSwipe pinch zoom, double-tap zoom, and panning. All
 * <captioned-image-gallery> elements on the page form a single navigation
 * cycle. The figure list is rebuilt each time the viewer opens, including
 * galleries added after page load.
 *
 * Markup:
 *   <captioned-image-gallery>
 *     <figure>
 *       <a href="full.jpg"><img src="thumb.jpg" alt="..."></a>
 *       <figcaption>caption text</figcaption>
 *     </figure>
 *     ...
 *   </captioned-image-gallery>
 *
 * Attributes:
 *   show-counter   Display "n / total" position counter in the lightbox
 *                  while viewing a figure from this gallery.
 *   max-row-items  Maximum number of figures in a justified row. Defaults
 *                  to 3.
 */

const STYLES = `
captioned-image-gallery:defined {
  --gap: 6px;
  --max-row-height: 240px;
  --single-image-max-height: var(--max-row-height);
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--gap);
  background: #f4f4f4;
  padding: var(--gap);
  border-radius: 4px;
}

captioned-image-gallery:defined > figure {
  margin: 0;
  position: relative;
  overflow: hidden;
  background: #ddd;
  border-radius: 2px;
  min-width: 0;
}

captioned-image-gallery:defined > figure > a {
  display: block;
  width: 100%;
  height: 100%;
  text-decoration: none;
  cursor: zoom-in;
}

captioned-image-gallery:defined img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

captioned-image-gallery:defined figcaption {
  position: absolute;
  bottom: 4px;
  left: 4px;
  right: 4px;
  margin: 0;
  padding: 2px 6px;
  font-size: 11px;
  color: white;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 2px;
  pointer-events: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

captioned-image-gallery:defined figcaption a {
  pointer-events: auto;
  color: inherit;
  text-decoration: none;
  border-bottom: none;
}

captioned-image-gallery:defined figcaption a:hover {
  color: #cfe8ff;
  text-decoration: none;
  border-bottom: none;
}

.captioned-gallery-pswp .pswp__gallery-caption {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px max(14px, env(safe-area-inset-bottom));
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 14px;
  line-height: 1.4;
  overflow-wrap: break-word;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.captioned-gallery-pswp.pswp--ui-visible .pswp__gallery-caption {
  opacity: 1;
}

.captioned-gallery-pswp .pswp__gallery-caption a {
  pointer-events: auto;
  color: #9cf;
  text-decoration: underline;
}

.captioned-gallery-pswp .captioned-gallery-counter {
  display: block;
  margin-bottom: 2px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
}

.captioned-gallery-pswp .captioned-gallery-counter[hidden] {
  display: none;
}
`;

function injectStyles() {
  if (document.getElementById('captioned-image-gallery-styles')) return;
  const style = document.createElement('style');
  style.id = 'captioned-image-gallery-styles';
  style.textContent = STYLES;
  document.head.appendChild(style);
}

class CaptionedImageGallery extends HTMLElement {
  static instances = new Set();
  static viewer = null;
  static opening = false;
  static photoSwipeAssets = null;

  connectedCallback() {
    this.figures = [...this.querySelectorAll(':scope > figure')];
    if (!this.figures.length) return;
    this.dataset.count = this.figures.length;

    CaptionedImageGallery.instances.add(this);

    // Wire up clicks on each figure's anchor: open the lightbox instead
    this.figures.forEach(figure => {
      const a = figure.querySelector('a');
      if (a && !a.dataset.captionedGalleryWired) {
        a.dataset.captionedGalleryWired = '1';
        a.addEventListener('click', e => {
          if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          e.preventDefault();
          a.focus({ preventScroll: true });
          CaptionedImageGallery.openFor(figure);
        });
      }
    });

    // Lay out as soon as we know an aspect ratio for every figure. When
    // each img carries data-width / data-height we can do this synchronously
    // and avoid the layout shift that comes from waiting on image loads.
    const imgs = this.figures.map(f => f.querySelector('img')).filter(Boolean);
    const ready = this.figures.every(f => this.declaredRatio(f) !== null);

    const setup = () => {
      this.applyLayout();
      this._lastWidth = this.clientWidth;
      this._ro = new ResizeObserver(entries => {
        const w = entries[0].contentRect.width;
        if (Math.abs(w - this._lastWidth) > 0.5) {
          this._lastWidth = w;
          this.applyLayout();
        }
      });
      this._ro.observe(this);
    };

    if (ready) {
      setup();
    } else {
      Promise.all(imgs.map(img => {
        if (img.complete && img.naturalWidth > 0) return Promise.resolve();
        return new Promise(res => {
          img.addEventListener('load', res, { once: true });
          img.addEventListener('error', res, { once: true });
        });
      })).then(setup);
    }
  }

  disconnectedCallback() {
    this._ro?.disconnect();
    CaptionedImageGallery.instances.delete(this);
  }

  declaredRatio(figure) {
    const img = figure.querySelector('img');
    if (!img) return null;
    const w = parseFloat(img.dataset.width);
    const h = parseFloat(img.dataset.height);
    if (isFinite(w) && isFinite(h) && w > 0 && h > 0) return w / h;
    return null;
  }

  ratioOf(figure) {
    const declared = this.declaredRatio(figure);
    if (declared !== null) return declared;
    const img = figure.querySelector('img');
    if (!img) return 1;
    const r = img.naturalWidth / img.naturalHeight;
    return isFinite(r) && r > 0 ? r : 1;
  }

  applyLayout() {
    const ratios = this.figures.map(f => this.ratioOf(f));
    const count = this.figures.length;

    this.figures.forEach(f => {
      f.style.width = '';
      f.style.height = '';
      f.style.aspectRatio = '';
      f.style.maxHeight = '';
    });

    const cs = getComputedStyle(this);
    const padL = parseFloat(cs.paddingLeft) || 0;
    const padR = parseFloat(cs.paddingRight) || 0;
    const gap = parseFloat(cs.gap) || 0;
    const containerW = this.clientWidth - padL - padR;
    const maxH = parseFloat(cs.getPropertyValue('--max-row-height')) || 240;
    const singleMaxH = (
      parseFloat(cs.getPropertyValue('--single-image-max-height')) || maxH
    );

    if (containerW <= 0) return;

    if (count === 1) {
      const f = this.figures[0];
      const r = ratios[0];
      this.dataset.orientation = r >= 1 ? 'landscape' : 'portrait';
      let h = singleMaxH;
      let w = h * r;
      if (w > containerW) {
        w = containerW;
        h = w / r;
      }
      f.style.width = w + 'px';
      f.style.height = h + 'px';
      return;
    }

    const splits = this.getRowSplits(count, this.maxRowItems());
    let idx = 0;
    splits.forEach(rowCount => {
      const rowFigs = this.figures.slice(idx, idx + rowCount);
      const rowRatios = ratios.slice(idx, idx + rowCount);
      const sum = rowRatios.reduce((a, b) => a + b, 0);
      const rowAvailW = Math.max(0, containerW - (rowCount - 1) * gap - 1);
      const naturalH = sum > 0 ? rowAvailW / sum : maxH;
      const rowH = Math.min(naturalH, maxH);
      rowFigs.forEach((f, i) => {
        f.style.width = (rowH * rowRatios[i]) + 'px';
        f.style.height = rowH + 'px';
      });
      idx += rowCount;
    });
  }

  maxRowItems() {
    const configured = parseInt(this.getAttribute('max-row-items'), 10);
    if (isFinite(configured) && configured >= 1 && configured <= 3) {
      return configured;
    }
    return 3;
  }

  getRowSplits(n, maxItems = 3) {
    if (maxItems <= 1) return Array.from({ length: n }, () => 1);
    if (maxItems === 2) {
      const splits = [];
      while (n > 0) {
        const rowCount = Math.min(2, n);
        splits.push(rowCount);
        n -= rowCount;
      }
      return splits;
    }

    if (n <= 3) return [n];
    // Cap rows at 3 wide. Use rows of 3 plus rows of 2 to make up the
    // remainder; smaller rows lead so the bottom row is the widest.
    const splits = [];
    const rem = n % 3;
    let twos, threes;
    if (rem === 0) {
      twos = 0;
      threes = n / 3;
    } else if (rem === 1) {
      twos = 2;
      threes = (n - 4) / 3;
    } else {
      twos = 1;
      threes = (n - 2) / 3;
    }
    for (let i = 0; i < twos; i++) splits.push(2);
    for (let i = 0; i < threes; i++) splits.push(3);
    return splits;
  }

  // ----- Cross-gallery flat list (in document order) -----

  static getAllFigures() {
    const sorted = [...CaptionedImageGallery.instances].sort((a, b) => {
      if (a === b) return 0;
      const pos = a.compareDocumentPosition(b);
      if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
      if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
      return 0;
    });
    const all = [];
    sorted.forEach(g => {
      [...g.querySelectorAll(':scope > figure')].forEach(f => all.push(f));
    });
    return all;
  }

  static loadPhotoSwipe() {
    if (!this.photoSwipeAssets) {
      const stylesheet = new Promise((resolve, reject) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = '/static/photoswipe/photoswipe.css';
        link.onload = resolve;
        link.onerror = () => {
          link.remove();
          reject(new Error('Could not load PhotoSwipe styles'));
        };
        document.head.appendChild(link);
      });
      this.photoSwipeAssets = Promise.all([
        import('/static/photoswipe/photoswipe.esm.min.js'),
        stylesheet,
      ]).then(([module]) => module.default).catch(error => {
        this.photoSwipeAssets = null;
        throw error;
      });
    }
    return this.photoSwipeAssets;
  }

  static slideData(figure) {
    const link = figure.querySelector('a');
    const thumb = figure.querySelector('img');
    // Stored dimensions describe the original. Older markup may only have
    // thumbnail dimensions; correct those when the full image finishes loading.
    return {
      src: link ? link.href : thumb.src,
      msrc: thumb.currentSrc || thumb.src,
      w: Number(thumb.dataset.width) || thumb.naturalWidth || 1,
      h: Number(thumb.dataset.height) || thumb.naturalHeight || 1,
      alt: thumb.alt,
      element: figure,
    };
  }

  static async openFor(figure) {
    if (!figure || this.viewer || this.opening) return;
    this.opening = true;
    try {
      const PhotoSwipe = await this.loadPhotoSwipe();
      const figures = this.getAllFigures().filter(f => f.querySelector('img'));
      const index = figures.indexOf(figure);
      if (index < 0) return;

      // PhotoSwipe 5.1 needs at least three slides for looping. Repeat a
      // two-photo set so swiping still wraps, as it did in the old viewer.
      const slides = (figures.length === 2 ? [...figures, ...figures] : figures)
        .map(f => this.slideData(f));
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const viewer = new PhotoSwipe(null, {
        dataSource: slides,
        index,
        mainClass: 'captioned-gallery-pswp',
        bgOpacity: 1,
        counter: false,
        allowMouseDrag: true,
        allowPanToNext: false,
        imageClickAction: 'zoom',
        showHideAnimationType: 'fade',
        showAnimationDuration: reducedMotion ? 0 : 200,
        hideAnimationDuration: reducedMotion ? 0 : 200,
        zoomAnimationDuration: reducedMotion ? 0 : 200,
        paddingFn: () => ({ top: 60, bottom: 64, left: 16, right: 16 }),
      });
      this.viewer = viewer;

      viewer.on('uiRegister', () => {
        viewer.ui.registerElement({
          name: 'gallery-caption',
          appendTo: 'root',
          onInit: el => {
            const counter = document.createElement('span');
            counter.className = 'captioned-gallery-counter';
            const caption = document.createElement('div');
            el.append(counter, caption);
            viewer.on('change', () => {
              const current = viewer.currSlide.data.element;
              const original = current.querySelector('figcaption');
              caption.replaceChildren();
              if (original) {
                for (const node of original.childNodes) {
                  caption.appendChild(node.cloneNode(true));
                }
              }
              counter.hidden = !current.closest('captioned-image-gallery').hasAttribute('show-counter');
              counter.textContent = `${figures.indexOf(current) + 1} / ${figures.length}`;
            });
          },
        });
      });

      const updateDimensions = ({ slide, isError }) => {
        if (isError) return;
        // Cached images can finish loading during slide construction.
        queueMicrotask(() => {
          if (!viewer.isOpen || viewer.isDestroying) return;
          const image = slide.content.element;
          if (!image?.naturalWidth || !image.naturalHeight) return;
          const { naturalWidth: width, naturalHeight: height } = image;
          if (slide.width === width && slide.height === height) return;
          slide.data.w = slide.content.width = slide.width = width;
          slide.data.h = slide.content.height = slide.height = height;
          slide.resize();
        });
      };
      viewer.on('loadComplete', updateDimensions);
      viewer.on('slideActivate', updateDimensions);
      viewer.on('destroy', () => { this.viewer = null; });
      viewer.init();
      viewer.template.setAttribute('aria-label', 'Photo gallery');
      viewer.template.setAttribute('aria-modal', 'true');
    } catch (error) {
      console.error('Could not open photo gallery', error);
      this.viewer?.destroy();
      this.viewer = null;
      // Preserve the image link if the optional viewer cannot load.
      const link = figure.querySelector('a');
      if (link) window.location.assign(link.href);
    } finally {
      this.opening = false;
    }
  }
}

injectStyles();

if (!customElements.get('captioned-image-gallery')) {
  customElements.define('captioned-image-gallery', CaptionedImageGallery);
}
