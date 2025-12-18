class ImageGallery extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.currentIndex = 0;
        // Bind the keydown handler so we can add/remove it properly
        this.handleKeyDown = this.handleKeyDown.bind(this);
    }

    static get observedAttributes() {
        return ['width'];
    }

    attributeChangedCallback() {
        this.render();
    }

    connectedCallback() {
        this.render();
        window.addEventListener('keydown', this.handleKeyDown);
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this.handleKeyDown);
    }

    // Helper to get the list of image elements from the slot
    getImages() {
        const slot = this.shadowRoot.querySelector('#gallery-slot');
        return slot.assignedElements().filter(el => el.tagName === 'IMG');
    }

    handleImageClick(e) {
        const img = e.target.closest('img');
        if (!img) return;

        const images = this.getImages();
        this.currentIndex = images.indexOf(img);
        
        this.updateModalContent();
        this.shadowRoot.querySelector('dialog').showModal();
    }

    handleKeyDown(e) {
        const dialog = this.shadowRoot.querySelector('dialog');
        // Only trigger if the modal is currently open
        if (!dialog.open) return;

        const images = this.getImages();
        if (images.length <= 1) return;

        if (e.key === 'ArrowRight') {
            this.currentIndex = (this.currentIndex + 1) % images.length;
            this.updateModalContent();
        } else if (e.key === 'ArrowLeft') {
            this.currentIndex = (this.currentIndex - 1 + images.length) % images.length;
            this.updateModalContent();
        }
    }

    updateModalContent() {
        const images = this.getImages();
        const activeImg = images[this.currentIndex];
        const modalImg = this.shadowRoot.querySelector('.modal-img');
        
        if (activeImg && modalImg) {
            modalImg.src = activeImg.dataset.fullsize || activeImg.src;
            modalImg.alt = activeImg.alt;
        }
    }

    render() {
        const cols = this.getAttribute('width') || 3;
        
        this.shadowRoot.innerHTML = `
        <style>
            :host {
                display: grid;
                grid-template-columns: repeat(${cols}, 1fr);
                gap: 10px;
                width: 100%;
            }

            ::slotted(img) {
                width: 100%;
                aspect-ratio: 1 / 1;
                object-fit: cover;
                cursor: pointer;
                display: block;
            }

            dialog {
                padding: 0;
                border: none;
                background: transparent;
                max-width: 95vw;
                max-height: 95vh;
                outline: none;
            }

            dialog::backdrop {
                background: rgba(0, 0, 0, 0.85);
            }

            .modal-container {
                position: relative;
                display: flex;
                justify-content: center;
                align-items: center;
            }

            .modal-img {
                max-width: 100%;
                max-height: 95vh;
                display: block;
                user-select: none;
            }

            .close-btn {
                position: absolute;
                top: 10px;
                right: 10px;
                background: none;
                border: none;
                color: white;
                font-size: 2.5rem;
                line-height: 1;
                cursor: pointer;
                padding: 0;
                width: 44px;
                height: 44px;
                opacity: 0.6;
                text-shadow: 0 0 10px rgba(0,0,0,0.5);
                outline: none;
                z-index: 10;
            }

            .close-btn:hover {
                opacity: 1;
            }
        </style>

        <slot id="gallery-slot"></slot>

        <dialog>
            <div class="modal-container">
                <form method="dialog">
                    <button class="close-btn" aria-label="Close modal">&times;</button>
                </form>
                <img class="modal-img" src="" alt="">
            </div>
        </dialog>
        `;

        this.setupImages();
        
        const dialog = this.shadowRoot.querySelector('dialog');
        dialog.addEventListener('click', (e) => {
            if (e.target === dialog) dialog.close();
        });
    }

    setupImages() {
        const images = this.getImages();

        images.forEach(img => {
            if (!img.dataset.fullsize) {
                img.dataset.fullsize = img.src;
            }
            if (img.dataset.thumb) {
                img.src = img.dataset.thumb;
            }
            // Use addEventListener instead of onclick to avoid overwriting other scripts
            img.onclick = (e) => this.handleImageClick(e);
        });
    }
}

customElements.define('image-gallery', ImageGallery);

