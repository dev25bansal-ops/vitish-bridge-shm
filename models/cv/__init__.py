"""cv — computer-vision crack detection for VITISH SHM.

YOLO-seg crack detection with a Canny/contour heuristic fallback, plus dataset
prep for SDNET2018 / Ultralytics CrackSeg9k / synthetic negatives.  The backend
reaches this via ``models.cv.inference.CrackDetector`` (cached process-wide by
backend/app/cv_feed.get_detector()); scripts/tests use the same entry point.

Module marker only — Python 3 namespace packages work without this file, but an
explicit package makes the import unambiguous on sys.path (a bare ``cv`` or
``fusion`` package anywhere upstream can no longer shadow ``models.cv``).
"""
