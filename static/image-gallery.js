
class ImageGallery extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    static get observedAttributes() {
        return ['width'];
    }

    attributeChangedCallback() {
        this.render();
    }

    connectedCallback() {
        this.render();
    }

    handleImageClick(e) {
        const img = e.target.closest('img');
        if (!img) return;

        const dialog = this.shadowRoot.querySelector('dialog');
        const modalImg = dialog.querySelector('.modal-img');
        
        modalImg.src = img.dataset.fullsize;
        modalImg.alt = img.alt;
        
        dialog.showModal();
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
                /* Removes the focus ring from the dialog element itself in some browsers */
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
                
                /* Remove border/outline on focus */
                outline: none;
            }

            /* Explicitly ensure no focus ring appears on the button */
            .close-btn:focus, 
            .close-btn:active,
            .close-btn:focus-visible {
                outline: none;
                border: none;
                box-shadow: none;
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
        const slot = this.shadowRoot.querySelector('#gallery-slot');
        const images = slot.assignedElements();

        images.forEach(img => {
            if (img.tagName === 'IMG') {
                if (!img.dataset.fullsize) {
                    img.dataset.fullsize = img.src;
                }
                if (img.dataset.thumb) {
                    img.src = img.dataset.thumb;
                }
                img.onclick = (e) => this.handleImageClick(e);
            }
        });
    }
}

customElements.define('image-gallery', ImageGallery);