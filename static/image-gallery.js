class ImageGallery extends HTMLElement {
  constructor() {
    super();
    this.processImages = this.processImages.bind(this);
  }

  async getImageDimensions(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve({ width: img.width, height: img.height });
      img.onerror = reject;
      img.src = url;
    });
  }

  async processImages() {
    const images = this.querySelectorAll('img');
    
    for (const img of images) {
      // Get original p tag parent
      const paragraph = img.parentElement;
      const src = img.src;
      const alt = img.alt;

      try {
        // Get image dimensions
        const dimensions = await this.getImageDimensions(src);

        // Create new structure
        const link = document.createElement('a');
        link.href = src;
        link.className = 'photoswipe-img';
        link.dataset.pswpWidth = dimensions.width;
        link.dataset.pswpHeight = dimensions.height;

        // Clone the image and set max-width
        const newImg = img.cloneNode(true);
        newImg.style.maxWidth = '100%';

        // Build new structure
        link.appendChild(newImg);
        paragraph.innerHTML = ''; // Clear paragraph
        paragraph.appendChild(link);
      } catch (error) {
        console.error(`Failed to process image: ${src}`, error);
      }
    }

    // Initialize PhotoSwipe
    this.initPhotoSwipe();
  }

  async initPhotoSwipe() {
    try {
      const { default: PhotoSwipeLightbox } = await import('/static/photoswipe/photoswipe-lightbox.esm.js');
      
      const lightbox = new PhotoSwipeLightbox({
        gallery: this,
        children: '.photoswipe-img',
        pswpModule: () => import('/static/photoswipe/photoswipe.esm.js')
      });
      
      lightbox.init();
    } catch (error) {
      console.error('Failed to initialize PhotoSwipe:', error);
    }
  }

  connectedCallback() {
    // Process images when the element is added to the document
    this.processImages();
  }
}

// Register the custom element
customElements.define('image-gallery', ImageGallery);
