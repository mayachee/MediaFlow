import logging
import math
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
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
        enhance: bool = True,
        crop_factor: float = 1.0,
        focal_point: tuple = (0.5, 0.5),
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
            with Image.open(image_path) as opened:
                img = ImageOps.exif_transpose(opened).convert('RGBA')
                canvas = Image.new('RGBA', img.size, (0, 0, 0, 255))
                img = Image.alpha_composite(canvas, img).convert('RGB')
            if not math.isfinite(crop_factor) or not 1 <= crop_factor <= 1.5:
                raise ValueError('Shot crop must be between 1 and 1.5')
            if len(focal_point) != 2 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in focal_point):
                raise ValueError('Focal point must contain two numbers between 0 and 1')
            if crop_factor > 1:
                width, height = img.width / crop_factor, img.height / crop_factor
                left = max(0, min(img.width - width, img.width * focal_point[0] - width / 2))
                top = max(0, min(img.height - height, img.height * focal_point[1] - height / 2))
                img = img.crop((round(left), round(top), round(left + width), round(top + height)))
            
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
            if enhance:
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
            max(1, math.ceil(orig_width * scale)),
            max(1, math.ceil(orig_height * scale)),
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
            max(1, min(self.target_width, round(orig_width * scale))),
            max(1, min(self.target_height, round(orig_height * scale))),
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
        motion: Optional[str] = None,
        zoom_factor: Optional[float] = None,
        beat_accents: Optional[List[dict]] = None,
        pulse_strength: float = 0.0,
        frames_per_image: int = 1,
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
        total_frames = max(1, int(duration * fps) - 1)
        zoom_factor = self.zoom_factor if zoom_factor is None else zoom_factor
        
        motion = motion or ('zoom_in' if zoom_in else 'zoom_out')
        if motion == 'zoom_in':
            # Zoom from 1.0 to zoom_factor
            zoom_expr = f"1.0+({zoom_factor}-1.0)*min(on/{total_frames},1)"
        elif motion == 'zoom_out':
            # Zoom from zoom_factor to 1.0
            zoom_expr = f"{zoom_factor}-({zoom_factor}-1.0)*min(on/{total_frames},1)"
        elif motion in {'pan_left', 'pan_right', 'pan_up', 'pan_down'}:
            zoom_expr = str(zoom_factor)
        else:
            raise ValueError(f'Unsupported moving-image motion: {motion}')
        if not math.isfinite(zoom_factor) or not 1 <= zoom_factor <= 2:
            raise ValueError('Scene zoom must be between 1 and 2')
        if not math.isfinite(pulse_strength) or not 0 <= pulse_strength <= 0.01:
            raise ValueError('Beat pulse strength must be between 0 and 0.01')
        accents = []
        for accent in (beat_accents or [])[:32]:
            time, strength = accent['time'], accent['strength']
            if not math.isfinite(time) or not math.isfinite(strength) or not 0 <= time <= duration or not 0 <= strength <= 1:
                raise ValueError('Invalid beat accent')
            accents.append(f'{strength:.5f}*exp(-60*pow(on/{fps}-{time:.5f},2))')
        if accents and pulse_strength:
            zoom_expr = f'min(2,({zoom_expr})+{pulse_strength}*(' + '+'.join(accents) + '))'
        progress = f'min(on/{total_frames},1)'
        x, y = 'iw/2-(iw/zoom/2)', 'ih/2-(ih/zoom/2)'
        if motion == 'pan_left':
            x = f'(iw-iw/zoom)*(1-{progress})'
        elif motion == 'pan_right':
            x = f'(iw-iw/zoom)*{progress}'
        elif motion == 'pan_up':
            y = f'(ih-ih/zoom)*(1-{progress})'
        elif motion == 'pan_down':
            y = f'(ih-ih/zoom)*{progress}'
        
        # Generate zoompan filter
        # x and y keep the image centered while zooming
        filter_str = (
            f"zoompan=z='{zoom_expr}':"
            f"x='{x}':"
            f"y='{y}':"
            f"d={frames_per_image}:"
            f"s={self.target_width}x{self.target_height}:"
            f"fps={fps}"
        )
        
        return filter_str
