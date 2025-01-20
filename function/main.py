import os
from google.cloud import firestore
from google.cloud import vision
import requests

def photo_analysis_service(event, context):
    bucket = os.environ.get('BUCKET', 'my-bmd-bucket1')
    file_name = event['name']

    objects = _analyze_photo(bucket, file_name)
    text = _extract_text(bucket, file_name)
    _store_results(bucket, file_name, objects, text)

def _analyze_photo(bucket, file_name):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(image_uri=f'gs://{bucket}/{file_name}'))
    objects = client.object_localization(image=image).localized_object_annotations
    return [obj.name for obj in objects]

def _extract_text(bucket, file_name):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(image_uri=f'gs://{bucket}/{file_name}'))
    response = client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description if texts else ""

def _store_results(bucket, file_name, objects, text):
    db = firestore.Client()
    for obj in objects:
        db.collection(u'tags').document(obj.lower()).set(
            {u'photo_urls': firestore.ArrayUnion(
                [f'https://storage.googleapis.com/{bucket}/{file_name}']
            )},
            merge=True
        )
    if text:
        db.collection(u'texts').document(file_name).set({"content": text})

def _reverse_search_and_store(bucket, file_name):
    """Simula la búsqueda inversa y almacena los resultados."""
    search_results = perform_reverse_search(f'gs://{bucket}/{file_name}')
    legitimacy_result = analyze_legitimacy(search_results)

    db = firestore.Client()
    db.collection(u'search_results').document(file_name).set({
        "legitimacy": legitimacy_result,
        "search_links": search_results.get("links", [])
    })


# Realizar la búsqueda inversa usando un servicio real (como TinEye o Google Images)
def perform_reverse_search(image_uri):
    """Realiza la búsqueda inversa usando una API externa como TinEye o Google Images."""

    # Aquí usaríamos TinEye o un servicio similar, pero como ejemplo, vamos a usar Google Custom Search
    api_key = 'YOUR_GOOGLE_API_KEY'
    cx = 'YOUR_GOOGLE_CX'  # El identificador de búsqueda de tu motor de búsqueda personalizada

    search_url = f"https://www.googleapis.com/customsearch/v1?q={image_uri}&key={api_key}&cx={cx}&searchType=image"

    response = requests.get(search_url)
    if response.status_code == 200:
        search_results = response.json()
        return {"links": [item['link'] for item in search_results.get('items', [])]}
    else:
        return {"links": []}

# Analizar la legitimidad de los resultados de la búsqueda inversa
def analyze_legitimacy(search_results):
    """Analiza la legitimidad basado en los resultados obtenidos en la búsqueda inversa."""
    if search_results.get("links"):
        # Si hay resultados, se podría realizar un análisis más profundo
        return "Legítimo"  # Ejemplo simplificado
    else:
        return "No evaluado"