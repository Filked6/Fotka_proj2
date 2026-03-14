## Wtyczka do Agisoft Metashape 
## Opis:
Wtyczka ma służyć do automatycznego wygenerowania modelu 3D i chmury punktów po uzupełnieniu odpowiednich danych w polach.
W samym skrypcie jest dodany zapis, aby projekt został na końcu zapisany. 
Należy jednak pamiętać, że podstawowa wersja Agisoft Metashape bez licencji pozwala na wykonywanie wszystkich funkcji, ale nie pozwala na zapisywanie czegokolwiek. 
Jeśli użytkownik nie będzie posiadać licencji to skrypt na końcu wyrzuci błąd, dlatego przed 1 uruchomieniem należy zakomendować te linijki kodu, które za to odpowiadają.

## Proces uruchamiania:
Po wejściu do Agisoft Metashape należy wcisnąć Ctrl + R co uruchomi okno z możliwością dodania skryptu.
W pierwszym polu należy wkleić ścieżkę do skryptu i kliknąć ok. 
Następnie w pasku u góry pojawi się FTP obok wszystkich innych narzędzi. 
Po kliknięciu we wtyczkę pojawi się okno w którym użytkownik musi wybrać następujące rzeczy:
* Ścieżkę do zdjęć, z których tworzony jest model,
* Kod EPSG dla zdjęć,
* Plik .txt, w którym zawarte są współrzędne punktów referencyjnych,
* Kod EPSG dla współrzędnych
* Jakość przetworzenia zdjęć
* Jakość chmury punktów
* Jakość modelu 3D
