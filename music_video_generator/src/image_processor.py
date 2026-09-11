import logging
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Process and prepare images for video generation."""
    
    def __init__(
        self,
        target_width: int = 1920,
        target_height: int = 1080,
        zoom_factor: float = 1.15,
    ):
        self.target_width = target_width
        self.target_height = target_height
        self.zoom_factor = zoom_factor
    
    def load_and_prepare(
        self,
        image_path: str,
        fit_to_screen: bool = True,
    ) -> Optional[Image.Image]:
        """
        Load and prepare image for video generation.
        
        Args:
            image_path: Path to image file
            fit_to_screen: If True, resize to fill screen with cropping
                          If False, resize to fit within screen
        
        Returns:
            Prepared PIL Image or None if failed
        """
        try:
            img = Image.open(image_path)
            
            # Convert to RGB if necessary
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            
            # Calculate scaling
            if fit_to_screen:
                # Fill the screen (may crop parts of image)
                img = self._fill_screen(img)
            else:
                # Fit within screen (may have letterboxing)
                img = self._fit_screen(img)
            
            # Enhance quality
            img = self._enhance_image(img)
            
            return img
            
        except Exception as e:
            logger.error(f"Failed to process image {image_path}: {e}")
            return None
    
    def _fill_screen(self, img: Image.Image) -> Image.Image:
        """Resize image to fill target dimensions (crop excess)."""
        orig_width, orig_height = img.size
        target_ratio = self.target_width / self.target_height
        orig_ratio = orig_width / orig_height
        
        if orig_ratio > target_ratio:
            # Image is wider, scale by height
            scale = self.target_height / orig_height
        else:
            # Image is taller, scale by width
            scale = self.target_width / orig_width
        
        new_size = (
            int(orig_width * scale),
            int(orig_height * scale),
        )
        
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Crop center
        left = (img.width - self.target_width) // 2
        top = (img.height - self.target_height) // 2
        right = left + self.target_width
        bottom = top + self.target_height
        
        img = img.crop((left, top, right, bottom))
        return img
    
    def _fit_screen(self, img: Image.Image) -> Image.Image:
        """Resize image to fit within target dimensions (letterbox)."""
        orig_width, orig_height = img.size
        target_ratio = self.target_width / self.target_height
        orig_ratio = orig_width / orig_height
        
        if orig_ratio > target_ratio:
            # Image is wider, scale by width
            scale = self.target_width / orig_width
        else:
            # Image is taller, scale by height
            scale = self.target_height / orig_height
        
        new_size = (
            int(orig_width * scale),
            int(orig_height * scale),
        )
        
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Create canvas and paste image centered
        canvas = Image.new("RGB", (self.target_width, self.target_height), (0, 0, 0))
        left = (self.target_width - img.width) // 2
        top = (self.target_height - img.height) // 2
        canvas.paste(img, (left, top))
        
        return canvas
    
    def _enhance_image(self, img: Image.Image) -> Image.Image:
        """Apply subtle enhancements to improve image quality."""
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        
        # Slightly increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.1)
        
        # Slightly increase color saturation
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.1)
        
        return img
    
    def generate_zoompan_filter(
        self,
        duration: float,
        zoom_in: bool = True,
        fps: int = 30,
    ) -> str:
        """
        Generate FFmpeg zoompan filter string for Ken Burns effect.
        
        Args:
            duration: Duration in seconds
            zoom_in: True for zoom in, False for zoom out
            fps: Frames per second
        
        Returns:
            FFmpeg filter string
        """
        total_frames = int(duration * fps)
        
        if zoom_in:
            # Zoom from 1.0 to zoom_factor
            zoom_expr = "1.0+(on/{}).5*(z-1.0)".format(total_frames)
        else:
            # Zoom from zoom_factor to 1.0
            zoom_expr = "z-(on/{}).5*(z-1.0)".format(total_frames)
        
        # Generate zoompan filter
        # x and y keep the image centered while zooming
        filter_str = (
            f"zoompan=z='{zoom_expr}':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:"
            f"s={self.target_width}x{self.target_height}:"
            f"fps={fps}"
        )
        
        return filter_str