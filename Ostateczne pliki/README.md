Oficjalnie w instrukcji ani w zadaniu na teams nie zostało napisane co trzeba wysłać (Chodzi o instrukcję do kodu), dlatego też jest plik readme.

Niestety podzczas realizacji ćwiczenia nie zobaczyłem, że do wykonania ćwiczenia na ocenę 5.0 nie trzeba wykonywać zadania na 4.0, dlatego w kodzie zostały zrealizowane wszystkie części. 

Cały kod został stworzony tak, aby mimo zachodzącej na siebie funkcjonalności z oceny 4.0 i 5.0 dało się go uruchomić z tym i tym. Zatem ćwiczenie powinno zawierać wszystkie zrealizowane rzeczy na ocenę 5.0.

Co do poszczególnych funkcjonalności funkcji to zostały one zapisane w formie komentarzy w kodzie odnośnie tego jak działają i czasami, dlaczego coś zostało zaimplementowane. 

Do uruchomienia zaś skryptu w Metashape należy doinstalować tam biblioteki openCV oraz numpy (jeżeli nie ma). Następnie należy wybrać ścieżki do folderu ze zdjęciami i pliku txt ze współrzędnymi punktów referencyjnych oraz układ współrzędnych (sam kod EPSG) dla zdjęć, punktów referencyjnych oraz układ końcowy.
Np. (według danych przykładowych):
- układ zdjęć: 4326
- układ punktów: 2178
- układ końcowy: 2180

Należy także wybrać jakość wyrównania,  chmury punktów oraz modelu 3D.

Podczas skryptu jest moment ręcznego mierzenia punktów (sygnalizowany komunikatem w okienku, trzeba zamknąć okienko, aby móc pomierzyć).
Jest także moment, w którym na ekranie nic nie jest pokazane oprócz okienka początkowego (moment z algorytmem fast do openCV), natomiast, skrypt się wtedy dalej wykonuje i należy chwilę poczekać.

Momentem zakończenia działania powinien być moment kiedy zamknie się okienko z wyborem rzeczy do uruchomienia automatycznego skryptu.

Koniec.

- Filip Kędzior, 331914