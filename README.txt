MORNING — PROVA LOCALE

File:
- update_feed.py: scarica l'API di Morning e aggiorna feed.xml
- feed.xml: feed di prova generato dai 20 episodi del JSON acquisito
- requirements.txt: dipendenza Python

Esecuzione su Windows:

1. Aprire il Prompt dei comandi nella cartella.
2. Installare requests:
   py -m pip install -r requirements.txt
3. Generare o aggiornare il feed:
   py update_feed.py

Comportamento:
- usa l'endpoint https://api-prod.ilpost.it/podcast/v3/bff/podcast/227474
- invia gli header apikey: testapikey e User-Agent: IlPostApp
- conserva nel feed gli episodi precedenti già presenti
- aggiunge gli episodi nuovi evitando duplicati tramite l'ID
- conserva al massimo 100 episodi, modificabile con MAX_EPISODES
- non contiene password, cookie o token personali

Questa è una prova locale. Non pubblicare ancora il feed.
