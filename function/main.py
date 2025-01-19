import os
from google.cloud import firestore
from google.cloud import vision

def photo_analysis_service(event, context):
    bucket = os.environ.get('BUCKET', 'my-bmd-bucket')
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
