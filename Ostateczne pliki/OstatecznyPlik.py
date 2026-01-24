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

        # obsługa przycisków
        self.ui.photosButton.clicked.connect(self.choose_photo_folder)
        self.ui.geodNetButton.clicked.connect(self.choose_geonet_file)
        self.ui.runButton.clicked.connect(self.start)

        # konfiguracja
        self.required_green_markers = 3
        self.required_photos_measured = 3
        self.check_interval = 2000

        self.advanced_monitor_timer = QtCore.QTimer()
        self.msg = QtWidgets.QMessageBox()

    def choose_photo_folder(self):
        #Okno do wyboru folderu ze zdjęciami
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Wybierz folder ze zdjęciami")
        if folder:
            self.ui.filePhotosEdit.setText(folder)

    def choose_geonet_file(self):
        #Okno do wyboru pliku z punktami referencyjnymi
        plik, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Wybierz plik osnowy", "",
                                                        "Pliki tekstowe (*.txt *.csv);;Wszystkie pliki (*.*)")
        if plik:
            self.ui.fileEditLine2.setText(plik)

    def start(self):
        #Uruchomienie wszystkiego po kliknięciu przycisku na końcu
        print("Uruchomiono proces!")
        self.sfmImageProcessing()
        self.first_part()

    def getAllImagesList(self, path):
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

    def show_info(self, message, time=10):
        #Okienko z tekstem do pokazywania wiadomości
        msg_w = QtWidgets.QMessageBox(self)
        msg_w.setText(message)
        msg_w.setStandardButtons(QtWidgets.QMessageBox.NoButton)
        msg_w.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        msg_w.show()
        QtCore.QTimer.singleShot(time * 1000, msg_w.close)

    def tellQualityInt(self, quality_type):
        #Konwersja typu z tekstu na liczbę mu odpowiadającą
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
        #Funkcja do łączenia markerów
        detected_markers = []
        reference_markers = []
        merged_dict = {}

        used_reference_labels = set()

        #Przypisujemy aktualne markery do ich kategorii
        for marker in self.chunk.markers:
            if marker.label.startswith("point"):
                detected_markers.append(marker)
            else:
                reference_markers.append(marker)

        #Początek łączenia
        for marker in detected_markers:
            #Pozyskujemy współrzędne dla wykrytych markerów (układ lokalny)
            if marker.position:
                pos_internal = marker.position
                pos_geodetic = self.chunk.crs.project(self.chunk.transform.matrix.mulp(pos_internal))

                xd = pos_geodetic.x
                yd = pos_geodetic.y
                zd = pos_geodetic.z

                dist = []
                for r_marker in reference_markers:
                    #Pozyskujemy współrzędne dla markerów referencyjnych (normalny układ)
                    if r_marker.label in used_reference_labels:
                        continue
                    if not r_marker.reference.location:
                        continue

                    source_location_r = r_marker.reference.location
                    xr = source_location_r.x
                    yr = source_location_r.y
                    zr = source_location_r.z

                    #Obliczamy odległość euklidesową (najprostsza metoda chyba)
                    odl = math.sqrt((xr - xd) ** 2 + (yr - yd) ** 2 + (zr - zd) ** 2)
                    dist.append((odl, r_marker.label))

                if dist:
                    #Wybieramy ten z najmniejszą
                    lowest = min(dist)
                    min_dist = lowest[0]
                    best_match_label = lowest[1]

                    merged_dict[marker.label] = best_match_label
                    used_reference_labels.add(best_match_label)

                    #Informacja o połączonych, tak o
                    print(f"Dopasowano: {marker.label} -> {best_match_label} (dist: {min_dist:.3f})")
                else:
                    print(f"Dla {marker.label} nie znaleziono wolnego markera referencyjnego.")

        markers_by_name = {m.label: m for m in self.chunk.markers}

        #Aby móc je łatwo połączyć to zmieniamy im nazwę, aby miały taką samo to się połączą
        #Punkt wykryty jest scalany z referencyjnym, aby uniknąć problemów
        for detected_name, reference_name in merged_dict.items():
            det_marker = markers_by_name.get(detected_name)
            ref_marker = markers_by_name.get(reference_name)
            if det_marker and ref_marker:
                for camera, projection in det_marker.projections.items():
                    ref_marker.projections[camera] = projection
                ref_marker.enabled = True

                self.chunk.remove(det_marker)

        #Odświeżamy na wrazie w
        self.chunk.updateTransform()

    def import_r_markers(self):
        #Funkcja do importu markerów referencyjnych (tych z pliczku)
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

    def count_ref_markers(self):
        #Funkcja do liczenia ilości potrzebnych markerów (wyjaśnienie po co dalej)
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
        #Pozyskanie parametrów
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

        #Rozpoczęcie fasta
        fast = cv2.FastFeatureDetector_create()
        fast.setThreshold(60)
        fast.setNonmaxSuppression(True)

        #Pozyskujemy współrzędne dla każdego markera w układzie lokalnym
        for marker in self.chunk.markers:
            geo_location = marker.reference.location
            loc_internal = self.chunk.crs.unproject(geo_location)

            xyz = np.array([loc_internal.x, loc_internal.y, loc_internal.z], dtype=np.float32)
            for camera in self.chunk.cameras:
                #Dla każdej kamery wyciągamy parametry
                if not camera.transform: #To ważne bo jak nie będzie miało to się wywali
                    continue
                m = camera.transform.inv()
                rotation_param = np.array([
                    [m[0, 0], m[0, 1], m[0, 2]],
                    [m[1, 0], m[1, 1], m[1, 2]],
                    [m[2, 0], m[2, 1], m[2, 2]]
                ], dtype=np.float32)

                translation_vect = np.array([m[0, 3], m[1, 3], m[2, 3]], dtype=np.float32).reshape(-1, 1)
                R, _ = cv2.Rodrigues(rotation_param)

                #Ustalenie marginesu w jakim szuka się się tego środka szachownicy (Nie za dużo bo kostka brukowa to mocny rywal)
                margin = 30

                points_2d, _ = cv2.projectPoints(xyz, R, translation_vect, K, dist)
                proj_x, proj_y = points_2d[0][0]

                #Zabezpieczenie przed wyjściem
                if not (margin < proj_x < sensor.width - margin and margin < proj_y < sensor.height - margin):
                    continue

                path = camera.photo.path
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

                x_start = int(proj_x - margin)
                y_start = int(proj_y - margin)
                x_end = int(proj_x + margin)
                y_end = int(proj_y + margin)

                #Ustalamy nasz zakres na zdjęciu gdzie szukamy
                roi = img[y_start:y_end, x_start:x_end]
                kp = fast.detect(roi, None)

                best_kp = None
                min_dist_local = float('inf')

                center_roi_x, center_roi_y = margin, margin

                #Sprawdzamy, który z wykrytych punków przez algorytm jest najlepszy, najbliższy środka
                for k in kp:
                    dx = k.pt[0] - center_roi_x
                    dy = k.pt[1] - center_roi_y
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < min_dist_local:
                        min_dist_local = d
                        best_kp = k

                #Ostateczne ustalenie najlepszego i zapisanie
                if best_kp and min_dist_local < 15:
                    final_x = x_start + best_kp.pt[0]
                    final_y = y_start + best_kp.pt[1]

                    #Zmieniamy współrzędne x, y
                    marker.projections[camera] = Metashape.Marker.Projection(Metashape.Vector([final_x, final_y]), pinned=True)

        #Odświeżamy widok i przeprowadzamy ostateczną orientację
        self.chunk.optimizeCameras(fit_f=True, fit_cx=True, fit_cy=True, fit_k1=True, fit_k2=True, fit_k3=True,
                                   fit_p1=True, fit_p2=True)
        self.chunk.updateTransform()

    def check_greens(self):
        #Funkcja do sprawdzenia czy użytkownik wyklikał już te 3 punkty na 3 zdjęciach
        fully_green = 0
        #Sprawdzamy co jakiś czas ile markerów jest pomierzonych z tych co mamy
        for marker in self.chunk.markers:
            if not marker.projections:
                continue
            green_on_this_marker = 0

            #Sprawdzenie czy dany marker jest pomierzony na 3 kamerach
            for camera, projection in marker.projections.items():
                if projection.pinned:
                    green_on_this_marker += 1

            #Jeżeli jest 3 to wtedy dodajemy ilość ogólnych "zielonych" markerów
            if green_on_this_marker >= self.required_photos_measured:
                fully_green += 1

        #Jeśli są 3 "zielone" to przepuszczamy dalej. Następnie zatrzymanie sprawdzania i wiadomość z wyborem dla użytkownika
        if fully_green >= self.required_green_markers:
            self.advanced_monitor_timer.stop()
            self.msg.setWindowTitle("Czas decyzji")
            self.msg.setText(
                "Czy chcesz kontynuować?\nTak - uruchomienie kolejnych etapów.\nNie - możliwość pomiaru dalszych punktów.")
            self.msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            self.msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
            result = self.msg.exec_()

            #Jeżeli użytkownik wybierze opcję nie to zwiększamy ilość "zielonych" aby można było pomierzyć więcej
            if result == QtWidgets.QMessageBox.No:
                self.advanced_monitor_timer.start(self.check_interval)
                self.required_green_markers += 1
            #jeśli tak to obliczamy jeszcze raz i przechodzimy do następnej części
            elif result == QtWidgets.QMessageBox.Yes:
                self.chunk.optimizeCameras(
                    fit_f=True, fit_cx=True, fit_cy=True,
                    fit_k1=True, fit_k2=True, fit_k3=True,
                    fit_p1=True, fit_p2=True, adaptive_fitting=True)

                self.chunk.updateTransform()

                self.next_part()

    def change_crsys(self):
        #Funkcja do zmiany współrzędnych
        epsg_geo_net = self.ui.coordsEdit2.text()
        epsg_photos = self.ui.coordsEdit1.text()
        epsg_end = self.ui.coordsEdit3.text()

        epsg_photos_full = f"EPSG::{epsg_photos}"
        epsg_geo_net_full = f"EPSG::{epsg_geo_net}"
        epsg_end_full = f"EPSG::{epsg_end}"

        crs_photos = Metashape.CoordinateSystem(epsg_photos_full)
        crs_geo_net = Metashape.CoordinateSystem(epsg_geo_net_full)
        crs_end = Metashape.CoordinateSystem(epsg_end_full)

        self.import_r_markers()

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

        #Mówimy Metashape, że teraz już te wszystkie rzeczy są w takich układach
        self.chunk.crs = crs_end
        self.chunk.camera_crs = crs_end
        self.chunk.marker_crs = crs_end

    def export_eo(self):
        #Funkcja do eksportu orientacji zewnętrznej
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

    def make_pc_model(self):
        #Tworzymy chmurę punktów i model w zależności od tego co uzytkownik sobie wybierze
        accuracy_point_cloud = self.ui.chooseQualityCloudPoint.currentText()
        accuracy_model_3d = self.ui.chooseQualityModel.currentText()

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

    def first_part(self):
        accuracy_match_photos = self.ui.chooseQualityOrient.currentText()
        Metashape.app.update()

        self.chunk.matchPhotos(downscale=self.tellQualityInt(accuracy_match_photos), generic_preselection=False, reference_preselection=False)
        self.chunk.alignCameras()

        length = self.count_ref_markers()

        #Automatyczna detekcja markerów
        self.chunk.detectMarkers(target_type=Metashape.TargetType.CrossTarget, tolerance=10)

        #Otóż detectMarkers nie zależnie od tego jaką dostanie mniejszą tolerancję (ostrzejszą) to i tak znajduje za dużo punktów
        #więc usuwamy nadmiarową ich liczbę tak aby później można było to połączyć z punktami referencyjnymi
        #Usuwamy te które zostały wykryte na jak najmniejszej liczbie zdjęć (Można też od końca ale ryzykowne, ale też działało jak testowałem)
        current_markers = list(self.chunk.markers)
        if len(current_markers) > length:
            current_markers.sort(key=lambda m: len(m.projections))
            to_remove_count = len(current_markers) - length
            markers_to_remove = current_markers[:to_remove_count]

            for marker in markers_to_remove:
                self.chunk.remove(marker)

        #Ręczne nadanie markerom "niebieskiej" flagi, mimo, że teoretycznie taką powinny mieć po detectMarkers, ale czasami to nie działało bez tego
        for marker in self.chunk.markers:
            for camera, projection in marker.projections.items():
                projection.pinned = False
                marker.projections[camera] = projection

        #Wyświetlenie okienka, aby użytkownik wiedział, że musi pomierzyć punkty i rozpoczęcie timera sprawdzającego "zielone markery"
        self.show_info("Pomierz conajmniej 3 punkty na 3 zdjęciach.")
        self.advanced_monitor_timer.timeout.connect(self.check_greens)
        self.advanced_monitor_timer.start(self.check_interval)

        self.check_greens()

    def next_part(self):
        photo_path = self.ui.filePhotosEdit.text()

        #Uruchomienie pozostałych funkcji w kolejności, tak aby wszystko zadziałało
        self.change_crsys()
        self.merge_markers()
        self.detect_rest_from_fast()
        self.export_eo()
        self.make_pc_model()

        #Zapis całego projektu i zamknięcie okienka, tak aby było wiadomo, że to już koniec
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

#Inicjalizacja całego kodu
def init_menu():
    Metashape.app.removeMenuItem("FTP")
    Metashape.app.addMenuItem("FTP", show_window)

init_menu()