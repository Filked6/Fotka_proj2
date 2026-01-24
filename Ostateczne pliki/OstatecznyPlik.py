from PySide2 import QtCore, QtWidgets
import Metashape
import glob
import math
from SkryptUi import Ui_WtykaFTP
import os
import cv2
import numpy as np

# Checking compatibility
compatible_major_version = "2.2"
found_major_version = ".".join(Metashape.app.version.split('.')[:2])
if found_major_version != compatible_major_version:
    raise Exception("Incompatible Metashape version: {} != {}".format(found_major_version, compatible_major_version))

class MyApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_WtykaFTP()
        self.ui.setupUi(self)

        self.doc = Metashape.app.document
        if len(self.doc.chunks) > 0:
            self.chunk = self.doc.chunks[0]
        else:
            self.chunk = self.doc.addChunk()

        self.ui.photosButton.clicked.connect(self.wybierz_folder_zdjec)
        self.ui.geodNetButton.clicked.connect(self.wybierz_plik_osnowy)
        self.ui.runButton.clicked.connect(self.uruchom_proces)

        # konfiguracja
        self.required_green_markers = 3
        self.required_photos_measured = 3
        self.check_interval = 2000

        self.advanced_monitor_timer = QtCore.QTimer()
        self.msg = QtWidgets.QMessageBox()

    def wybierz_folder_zdjec(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Wybierz folder ze zdjęciami")
        if folder:
            self.ui.filePhotosEdit.setText(folder)

    def wybierz_plik_osnowy(self):
        plik, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Wybierz plik osnowy", "",
                                                        "Pliki tekstowe (*.txt *.csv);;Wszystkie pliki (*.*)")
        if plik:
            self.ui.fileEditLine2.setText(plik)

    def uruchom_proces(self):
        print("Uruchomiono proces!")
        self.sfmImageProcessing()
        self.przetwarzankoZDJ()

    def getAllImagesList(self, path):
        import os
        search_path = os.path.join(path, "*.jpg")
        files_jpg = glob.glob(search_path)
        return files_jpg

    def sfmImageProcessing(self):
        path = self.ui.filePhotosEdit.text()

        if not path:
            print("Nie wybrano ścieżki!")
            return

        image_list = self.getAllImagesList(path)

        print(f"Znaleziono zdjęć: {len(image_list)}")
        print(image_list)

        if image_list:
            self.chunk.addPhotos(image_list, load_xmp_orientation=True)
        else:
            print("Lista zdjęć jest pusta.")

    def tellQualityInt(self, quality_type):
        if quality_type == "Ultra low":
            return 8
        elif quality_type == "Low":
            return 4
        elif quality_type == "Medium":
            return 2
        elif quality_type == "High":
            return 1
        elif quality_type == "Ultra high":
            return 0.5
        else:
            return ValueError("Nieznana jakość")

    def merge_markers(self):
        detected_markers = []
        reference_markers = []
        merged_dict = {}

        used_reference_labels = set()

        for marker in self.chunk.markers:
            if marker.label.startswith("point"):
                detected_markers.append(marker)
            else:
                reference_markers.append(marker)

        for marker in detected_markers:
            if marker.position:
                pos_internal = marker.position
                pos_geodetic = self.chunk.crs.project(self.chunk.transform.matrix.mulp(pos_internal))

                xd = pos_geodetic.x
                yd = pos_geodetic.y
                zd = pos_geodetic.z

                dist = []
                for r_marker in reference_markers:
                    if r_marker.label in used_reference_labels:
                        continue
                    if not r_marker.reference.location:
                        continue

                    source_location_r = r_marker.reference.location
                    xr = source_location_r.x
                    yr = source_location_r.y
                    zr = source_location_r.z

                    odl = math.sqrt((xr - xd) ** 2 + (yr - yd) ** 2 + (zr - zd) ** 2)
                    dist.append((odl, r_marker.label))

                if dist:
                    lowest = min(dist)
                    min_dist = lowest[0]
                    best_match_label = lowest[1]

                    merged_dict[marker.label] = best_match_label
                    used_reference_labels.add(best_match_label)

                    print(f"Dopasowano: {marker.label} -> {best_match_label} (dist: {min_dist:.3f})")
                else:
                    print(f"Dla {marker.label} nie znaleziono wolnego markera referencyjnego.")

        markers_by_name = {m.label: m for m in self.chunk.markers}

        for detected_name, reference_name in merged_dict.items():
            det_marker = markers_by_name.get(detected_name)
            ref_marker = markers_by_name.get(reference_name)
            if det_marker and ref_marker:
                for camera, projection in det_marker.projections.items():
                    ref_marker.projections[camera] = projection
                ref_marker.enabled = True

                self.chunk.remove(det_marker)

        self.chunk.updateTransform()

    def export_eo(self):
        photo_path = self.ui.filePhotosEdit.text()
        path = os.path.join(photo_path, "exteriorOrientation.txt")

        self.chunk.exportReference(
            path=path,
            format=Metashape.ReferenceFormatCSV,
            items=Metashape.ReferenceItemsCameras,
            columns="nuvwdef",  # n=Label, u/v/w=estimated coordinates, d/e/f=estimated coordination angles
            delimiter=",",
            precision=6
        )

        print(f"Zapisano orientację do: {path}")

    def import_r_markers(self):
        geonet_path = self.ui.fileEditLine2.text()
        epsg_geo_net = self.ui.coordsEdit2.text()
        epsg_geo_net_full = f"EPSG::{epsg_geo_net}"
        crs_geo_net = Metashape.CoordinateSystem(epsg_geo_net_full)

        self.chunk.importReference(
            path=geonet_path,
            format=Metashape.ReferenceFormatCSV,
            columns="nyxz",
            delimiter="\t",
            crs=crs_geo_net,
            skip_rows=0,
            ignore_labels=False,
            create_markers=True
        )

        return len(self.chunk.markers)

    def count_ref_markers(self):
        geonet_path = self.ui.fileEditLine2.text()
        marker_quantity = 0
        with open(geonet_path, 'r') as f:
            for line in f:
                if line.strip():
                    marker_quantity += 1
        return marker_quantity

    def detect_rest_from_fast(self):
        """
        #Problem jest taki, że Metashape w wersji demo nie da rady tego chyba zapisać, dlatego będzie to ręcznie obsłużone
        #aby można było sprawdzić czy działa

        path = os.path.join(photo_path, "in_orient.xml")
        sensor = self.chunk.sensors[0]
        sensor.calibration.save(path, format=Metashape.CalibrationFormat.CalibrationFormatOpenCV)

        fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
        K = fs.getNode("camera_matrix").mat()
        dist = fs.getNode("distortion_coefficients").mat()
        fs.release()
        """
        print("Wykrywanie pozostałych punktów...")
        sensor = self.chunk.sensors[0]
        calib = sensor.calibration

        width = sensor.width
        height = sensor.height

        K = np.array([
            [calib.f, 0, calib.cx + width / 2],
            [0, calib.f, calib.cy + height / 2],
            [0, 0, 1]
        ], dtype=np.float32)

        dist = np.array([calib.k1, calib.k2, calib.p1, calib.p2, calib.k3], dtype=np.float32)

        fast = cv2.FastFeatureDetector_create()
        fast.setThreshold(60)
        fast.setNonmaxSuppression(True)

        for marker in self.chunk.markers:
            geo_location = marker.reference.location
            loc_internal = self.chunk.crs.unproject(geo_location)

            xyz = np.array([loc_internal.x, loc_internal.y, loc_internal.z], dtype=np.float32)
            for camera in self.chunk.cameras:
                if not camera.transform:
                    continue
                m = camera.transform.inv()
                rotation_list = np.array([
                    [m[0, 0], m[0, 1], m[0, 2]],
                    [m[1, 0], m[1, 1], m[1, 2]],
                    [m[2, 0], m[2, 1], m[2, 2]]
                ], dtype=np.float32)

                translation_list = np.array([m[0, 3], m[1, 3], m[2, 3]], dtype=np.float32).reshape(-1, 1)
                R, _ = cv2.Rodrigues(rotation_list)

                margin = 30

                points_2d, _ = cv2.projectPoints(xyz, R, translation_list, K, dist)
                proj_x, proj_y = points_2d[0][0]

                if not (margin < proj_x < sensor.width - margin and margin < proj_y < sensor.height - margin):
                    continue

                path = camera.photo.path
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

                x_start = int(proj_x - margin)
                y_start = int(proj_y - margin)
                x_end = int(proj_x + margin)
                y_end = int(proj_y + margin)

                roi = img[y_start:y_end, x_start:x_end]
                kp = fast.detect(roi, None)

                best_kp = None
                min_dist_local = float('inf')

                center_roi_x, center_roi_y = margin, margin

                for k in kp:
                    dx = k.pt[0] - center_roi_x
                    dy = k.pt[1] - center_roi_y
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < min_dist_local:
                        min_dist_local = d
                        best_kp = k

                if best_kp and min_dist_local < 15:
                    final_x = x_start + best_kp.pt[0]
                    final_y = y_start + best_kp.pt[1]

                    marker.projections[camera] = Metashape.Marker.Projection(Metashape.Vector([final_x, final_y]), pinned=True)

        self.chunk.optimizeCameras(fit_f=True, fit_cx=True, fit_cy=True, fit_k1=True, fit_k2=True, fit_k3=True,
                                   fit_p1=True, fit_p2=True)
        self.chunk.updateTransform()

    def check_greens(self):
        fully_green = 0
        for marker in self.chunk.markers:
            if not marker.projections:
                continue

            green_on_this_marker = 0
            for camera, projection in marker.projections.items():
                if projection.pinned:
                    green_on_this_marker += 1

            if green_on_this_marker >= self.required_photos_measured:
                fully_green += 1

        if fully_green >= self.required_green_markers:
            self.advanced_monitor_timer.stop()
            self.msg.setWindowTitle("Czas decyzji")
            self.msg.setText(
                "Czy chcesz kontynuować?\nTak - uruchomienie kolejnych etapów.\nNie - możliwość pomiaru dalszych punktów.")
            self.msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            self.msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
            result = self.msg.exec_()

            if result == QtWidgets.QMessageBox.No:
                self.advanced_monitor_timer.start(self.check_interval)
                self.required_green_markers += 1
            elif result == QtWidgets.QMessageBox.Yes:
                self.chunk.optimizeCameras(
                    fit_f=True, fit_cx=True, fit_cy=True,
                    fit_k1=True, fit_k2=True, fit_k3=True,
                    fit_p1=True, fit_p2=True, adaptive_fitting=True)

                self.chunk.updateTransform()

                self.next_part()

    def przetwarzankoZDJ(self):
        accuracy_match_photos = self.ui.chooseQualityOrient.currentText()
        ####################################################################

        Metashape.app.update()

        self.chunk.matchPhotos(downscale=self.tellQualityInt(accuracy_match_photos), generic_preselection=False,
                               reference_preselection=False)
        self.chunk.alignCameras()

        length = self.count_ref_markers()

        self.chunk.detectMarkers(target_type=Metashape.TargetType.CrossTarget, tolerance=10)

        current_markers = list(self.chunk.markers)

        if len(current_markers) > length:
            current_markers.sort(key=lambda m: len(m.projections))
            to_remove_count = len(current_markers) - length
            markers_to_remove = current_markers[:to_remove_count]

            for marker in markers_to_remove:
                self.chunk.remove(marker)

        for marker in self.chunk.markers:
            for camera, projection in marker.projections.items():
                projection.pinned = False
                marker.projections[camera] = projection

        self.advanced_monitor_timer.timeout.connect(self.check_greens)
        self.advanced_monitor_timer.start(self.check_interval)

        self.check_greens()

    def next_part(self):
        accuracy_point_cloud = self.ui.chooseQualityCloudPoint.currentText()
        accuracy_model_3d = self.ui.chooseQualityModel.currentText()
        epsg_geo_net = self.ui.coordsEdit2.text()
        epsg_geo_net_full = f"EPSG::{epsg_geo_net}"
        crs_geo_net = Metashape.CoordinateSystem(epsg_geo_net_full)
        photo_path = self.ui.filePhotosEdit.text()
        epsg_photos = self.ui.coordsEdit1.text()
        epsg_end = self.ui.coordsEdit3.text()

        epsg_photos_full = f"EPSG::{epsg_photos}"
        epsg_end_full = f"EPSG::{epsg_end}"

        crs_photos = Metashape.CoordinateSystem(epsg_photos_full)
        crs_end = Metashape.CoordinateSystem(epsg_end_full)

        _ = self.import_r_markers()

        if epsg_geo_net != epsg_end:
            for marker in self.chunk.markers:
                if not marker.label.startswith("point"):
                    if not marker.reference.location:
                        continue
                    marker_location = marker.reference.location
                    final_marker_location = Metashape.CoordinateSystem.transform(marker_location, crs_geo_net, crs_end)
                    marker.reference.location = final_marker_location

        if epsg_photos != epsg_end:
            for camera in self.chunk.cameras:
                if not camera.reference.location: continue
                camera_location = camera.reference.location
                final_camera_location = Metashape.CoordinateSystem.transform(camera_location, crs_photos, crs_end)
                camera.reference.location = final_camera_location

        self.chunk.crs = crs_end
        self.chunk.camera_crs = crs_end
        self.chunk.marker_crs = crs_end

        self.merge_markers()
        self.detect_rest_from_fast()
        self.export_eo()

        if self.ui.modelBox.isChecked():
            if accuracy_point_cloud == accuracy_model_3d:
                self.chunk.buildDepthMaps(downscale=self.tellQualityInt(accuracy_point_cloud),
                                          filter_mode=Metashape.AggressiveFiltering)
                if self.ui.cloudPointBox.isChecked():
                    self.chunk.buildPointCloud()
                self.chunk.buildModel(source_data=Metashape.DepthMapsData, surface_type=Metashape.Arbitrary,
                                      interpolation=Metashape.EnabledInterpolation)
                self.chunk.buildUV(mapping_mode=Metashape.GenericMapping)
            else:
                if self.ui.cloudPointBox.isChecked():
                    self.chunk.buildDepthMaps(downscale=self.tellQualityInt(accuracy_point_cloud),
                                              filter_mode=Metashape.AggressiveFiltering)
                    self.chunk.buildPointCloud()
                self.chunk.buildDepthMaps(downscale=self.tellQualityInt(accuracy_model_3d),
                                          filter_mode=Metashape.AggressiveFiltering)
                self.chunk.buildModel(source_data=Metashape.DepthMapsData, surface_type=Metashape.Arbitrary,
                                      interpolation=Metashape.EnabledInterpolation)
                self.chunk.buildUV(mapping_mode=Metashape.GenericMapping)

        # save document
        document_name = "wtykaFTP.psx"
        document_path = os.path.join(photo_path, document_name)
        self.doc.save(document_path)

        self.close()

app_window = None

def show_window():
    global app_window

    if app_window is None:
        app_window = MyApp()

    app_window.show()

def init_menu():
    Metashape.app.addMenuItem("FTP", show_window)

init_menu()