"""
Real demo photography for `seed_cozy`.

All IDs below are Unsplash photos published under the free Unsplash License
(https://unsplash.com/license): free for commercial use, no attribution required.
They are downloaded on *your* machine when you run `python manage.py seed_cozy`.
Replace them with your own product photography before going live — demo photos
do not show COZY's actual products.
"""
import io
import logging
import urllib.error
import urllib.request

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

PHOTOS = {
    "Earrings": ["jVPAwMAcNjM", "uqol_kiM3vQ", "mbSmroQl_V0", "aFuFjTGoq6U", "QGSxt40LyWw", "PsQuMau8m5A",
                 "47h4o-KNVpk"],
    "Necklaces": ["QMBar9xvhMU", "j8K6eiBzG_g", "rlIJauOk4Rc", "TxCbfMc854c", "DXmhzif5izc", "j2AocKcXQ4k",
                  "e1pWGcMEaqU", "jYb0W5z10jI"],
    "Bracelets": ["V7aUwlZvDLo", "6AULRZxKHQc", "rGz2Z6tVaeg", "chxchUQDeQE", "_wK5BaXTaPs", "9_7Z__RDau0",
                  "lC-Lbfy-Q_A", "87iLRaZlyjg", "80YbFFiWIaQ"],
    "Rings": ["Kamw9QyG0Zk", "orVNEDAylaU", "CtZZAif-WfQ", "BN0HcaBdPug", "9RIKqgYUWX4", "NYqEk7a42yc",
              "b0OVnKVhqkw", "uAqAcmiiTuI", "2YmtU5RUbzU", "Fx4ODZu1gTQ", "CGpd5fSUHkw"],
    "Anklets": ["chxchUQDeQE", "80YbFFiWIaQ", "_wK5BaXTaPs", "rGz2Z6tVaeg"],
    "Jewellery Sets": ["aldDZePniqg", "ElpKzh2RVrc", "JaT8kpTQWpI", "esAis38NHT8", "SqYcPuUG1W4"],
    "Hair Accessories": ["hs5IsRAFgMo", "zlIVqqgi5IU", "QMBar9xvhMU"],
    "Fashion Accessories": ["esAis38NHT8", "TxCbfMc854c", "47h4o-KNVpk", "j2AocKcXQ4k"],
    "Gift Items": ["NgdKNonDF7Y", "ZA5EpwKOTeA", "3BvVFcZIL7I", "VfWkdMue5Jc", "bNPIoil02tU"],
}
# Lifestyle / model shots for hero slides, promo tiles, brand story and blog.
HERO = ["UBeNYvk6ED0", "SqYcPuUG1W4", "yXKCMbQ3F80"]
PROMO = ["NgdKNonDF7Y", "aldDZePniqg"]
OFFER = "esAis38NHT8"
BRAND = "ZNCvl62paUo"
BLOG = "Tz1NMeucwqE"
SOCIAL = ["_v7M3y2i3bU", "uqol_kiM3vQ", "NYqEk7a42yc", "6AULRZxKHQc", "UBeNYvk6ED0", "lC-Lbfy-Q_A"]

USER_AGENT = {"User-Agent": "COZY-seed/1.0 (+https://github.com/jincyrajeevan0811/COZY)"}


class PhotoFetcher:
    """Downloads cropped Unsplash images (cached per id/size). Gives up quietly when offline."""

    def __init__(self, enabled=True, stdout=None):
        self.enabled = enabled
        self.stdout = stdout
        self.cache = {}
        self.base_urls = {}
        self.failures = 0
        self.ok = 0

    def _log(self, msg):
        if self.stdout:
            self.stdout.write(msg)

    def _base_url(self, photo_id):
        if photo_id not in self.base_urls:
            req = urllib.request.Request(f"https://unsplash.com/photos/{photo_id}/download?force=true",
                                         headers=USER_AGENT)
            with urllib.request.urlopen(req, timeout=20) as resp:  # follows the redirect to images.unsplash.com
                final = resp.geturl()
            if "images.unsplash.com" not in final:
                raise ValueError(f"unexpected redirect for {photo_id}")
            self.base_urls[photo_id] = final
        return self.base_urls[photo_id]

    def get(self, photo_id, width, height):
        """Return a ContentFile (JPEG) or None when the photo cannot be fetched."""
        if not self.enabled or not photo_id:
            return None
        key = (photo_id, width, height)
        if key in self.cache:
            data = self.cache[key]
            return ContentFile(data) if data else None
        data = None
        try:
            base = self._base_url(photo_id)
            sep = "&" if "?" in base else "?"
            url = f"{base}{sep}w={width}&h={height}&fit=crop&crop=entropy&q=80&fm=jpg"
            with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=30) as resp:
                data = resp.read()
            from PIL import Image

            Image.open(io.BytesIO(data)).verify()
            self.ok += 1
        except (urllib.error.URLError, OSError, ValueError) as exc:
            data = None
            self.failures += 1
            if self.failures == 1:
                self._log(f"  ! Could not download photo {photo_id} ({exc}). Using generated artwork where needed.")
            if self.failures >= 5 and self.ok == 0:
                self._log("  ! No internet access to Unsplash — switching to generated artwork for the rest.")
                self.enabled = False
        self.cache[key] = data
        return ContentFile(data) if data else None

    def pick(self, category, index):
        ids = PHOTOS.get(category) or PHOTOS["Necklaces"]
        return ids[index % len(ids)]
