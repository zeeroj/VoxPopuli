import os
import pickle
import tempfile
import cv2
import numpy as np
from config import CANDIDATES, FACE_CACHE_PATH, DATA_DIR
from duckduckgo_search import DDGS
import requests


class FaceMatcher:
    def __init__(self):
        self.recognizer = None
        self.label_map = {}
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        self._load_cache()

    def _load_cache(self):
        model_path = os.path.join(DATA_DIR, "face_recognizer.yml")
        label_path = os.path.join(DATA_DIR, "face_labels.pkl")
        if os.path.exists(model_path) and os.path.exists(label_path):
            try:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create()
                self.recognizer.read(model_path)
                with open(label_path, "rb") as f:
                    self.label_map = pickle.load(f)
            except Exception:
                self.recognizer = None
                self.label_map = {}

    def _save_cache(self):
        if self.recognizer is None:
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        model_path = os.path.join(DATA_DIR, "face_recognizer.yml")
        label_path = os.path.join(DATA_DIR, "face_labels.pkl")
        self.recognizer.write(model_path)
        with open(label_path, "wb") as f:
            pickle.dump(self.label_map, f)

    def _detect_faces(self, image_path):
        image = cv2.imread(image_path)
        if image is None:
            return [], None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces_rect = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        face_imgs = []
        for (x, y, w, h) in faces_rect:
            face_img = gray[y:y + h, x:x + w]
            face_img = cv2.resize(face_img, (150, 150))
            face_imgs.append(face_img)
        return face_imgs, image

    def _download_reference_faces(self, candidate_key):
        candidate = CANDIDATES.get(candidate_key)
        if not candidate:
            return []

        search_query = f"{candidate['name']} cara foto oficial retrato primer plano rostro"
        images_downloaded = []

        try:
            with DDGS() as ddgs:
                img_results = list(ddgs.images(search_query, max_results=8))
        except Exception:
            return []

        for img_result in img_results:
            img_url = img_result.get("image")
            if not img_url:
                continue
            try:
                resp = requests.get(img_url, timeout=10)
                resp.raise_for_status()
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp.write(resp.content)
                tmp.close()

                faces, _ = self._detect_faces(tmp.name)
                os.unlink(tmp.name)

                for face in faces:
                    images_downloaded.append(face)

                if len(images_downloaded) >= 5:
                    break
            except Exception:
                continue

        return images_downloaded

    def ensure_candidate_encodings(self):
        if self.recognizer is not None and len(self.label_map) > 0:
            return

        training_faces = []
        training_labels = []
        next_label = 0

        for candidate_key, info in CANDIDATES.items():
            faces = self._download_reference_faces(candidate_key)
            if faces:
                self.label_map[next_label] = candidate_key
                for face in faces:
                    training_faces.append(face)
                    training_labels.append(next_label)
                next_label += 1

        if training_faces:
            self.recognizer = cv2.face.LBPHFaceRecognizer_create()
            self.recognizer.train(training_faces, np.array(training_labels))
            self._save_cache()

    def identify_person(self, image_path):
        if not os.path.exists(image_path) or self.recognizer is None:
            return []

        try:
            faces, _ = self._detect_faces(image_path)
        except Exception:
            return []

        results = []
        for face in faces:
            try:
                label, confidence = self.recognizer.predict(face)
                inv_confidence = max(0.0, min(1.0, 1.0 - (confidence / 100.0)))
                if inv_confidence > 0.40:
                    candidate_key = self.label_map.get(label)
                    if candidate_key:
                        results.append({
                            "candidate_key": candidate_key,
                            "confidence": round(inv_confidence, 3),
                            "candidate_name": CANDIDATES.get(candidate_key, {}).get("name", candidate_key),
                        })
            except Exception:
                continue

        return sorted(results, key=lambda x: x["confidence"], reverse=True)

    def identify_in_url(self, image_url, download_fn):
        if not image_url:
            return []
        tmp_path = download_fn(image_url)
        if not tmp_path:
            return []
        try:
            return self.identify_person(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
