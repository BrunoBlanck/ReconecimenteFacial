from flask import Flask, request, jsonify
import sqlite3
import os
import uuid
import json
from io import BytesIO
import numpy as np
import face_recognition
from PIL import Image 
import base64
from flask_cors import CORS


app = Flask(__name__, static_url_path='/', static_folder='src')
CORS(app)
# Cria a pasta para armazenar as imagens, se não existir
if not os.path.exists('imagens'):
    os.makedirs('imagens')


def salvaIMG(image_bytes, original_filename, file_uuid=None):
    if file_uuid is None:
        file_uuid = str(uuid.uuid4())
    ext = os.path.splitext(original_filename)[1] if '.' in original_filename else '.jpg'
    filename = file_uuid + ext

    # Salva a imagem original em /imagens
    if not os.path.exists('imagens'):
        os.makedirs('imagens')
    original_path = os.path.join('imagens', filename)
    with open(original_path, 'wb') as f:
        f.write(image_bytes)

    # Salva a imagem redimensionada em /src/img (máximo de 500px, mantendo a proporção)
    if not os.path.exists('src/img'):
        os.makedirs('src/img')
    img_pil = Image.open(BytesIO(image_bytes))
    img_pil.thumbnail((500, 500), Image.LANCZOS)
    resized_path = os.path.join('src/img', filename)
    img_pil.save(resized_path)

    return filename

# Inicializa o banco de dados SQLite e cria a tabela se necessário
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS pessoas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT NOT NULL,
        nome TEXT NOT NULL,
        telefone TEXT NOT NULL,
        endereco TEXT NOT NULL,
        ativo INTEGER NOT NULL,
        image_filename TEXT NOT NULL,
        face_encoding TEXT NOT NULL
    )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return app.send_static_file('index.html')

# EndPoint /upload: Recebe imagem e dados, valida se há exatamente uma face e salva tudo
@app.route('/upload', methods=['POST'])
def upload():
    nome = request.form.get('nome')
    telefone = request.form.get('telefone')
    endereco = request.form.get('endereco')
    ativo = request.form.get('ativo')
    image_file = request.files.get('image')

    if not all([nome, telefone, endereco, ativo, image_file]):
        return jsonify({'error': 'Todos os dados são obrigatórios.'}), 400

    try:
        ativo_int = int(ativo)
    except Exception:
        return jsonify({'error': 'Campo ativo deve ser numérico.'}), 400

    try:
        image_bytes = image_file.read()
        img = face_recognition.load_image_file(BytesIO(image_bytes))
    except Exception:
        return jsonify({'error': 'Imagem inválida.'}), 400

    face_locations = face_recognition.face_locations(img)
    if len(face_locations) != 1:
        return jsonify({'error': 'A imagem deve conter exatamente uma face.'}), 400

    encodings = face_recognition.face_encodings(img, face_locations)
    if not encodings:
        return jsonify({'error': 'Não foi possível gerar encoding da face.'}), 400
    face_encoding = encodings[0].tolist()

    file_uuid = str(uuid.uuid4())
    filename = salvaIMG(image_bytes, image_file.filename, file_uuid)

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO pessoas (uuid, nome, telefone, endereco, ativo, image_filename, face_encoding)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (file_uuid, nome, telefone, endereco, ativo_int, filename, json.dumps(face_encoding)))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Upload realizado com sucesso.'}), 200


@app.route('/update/<user_uuid>', methods=['PUT'])
def update_user(user_uuid):
    nome = request.form.get('nome')
    telefone = request.form.get('telefone')
    endereco = request.form.get('endereco')
    ativo = request.form.get('ativo')
    image_file = request.files.get('image')

    if not any([nome, telefone, endereco, ativo, image_file]):
        return jsonify({'error': 'Pelo menos um campo deve ser fornecido para atualização.'}), 400

    update_fields = []
    params = []

    if nome:
        update_fields.append("nome = ?")
        params.append(nome)
    if telefone:
        update_fields.append("telefone = ?")
        params.append(telefone)
    if endereco:
        update_fields.append("endereco = ?")
        params.append(endereco)
    if ativo:
        try:
            ativo_int = int(ativo)
        except Exception:
            return jsonify({'error': 'Campo ativo deve ser numérico.'}), 400
        update_fields.append("ativo = ?")
        params.append(ativo_int)

    if image_file:
        try:
            image_bytes = image_file.read()
            img = face_recognition.load_image_file(BytesIO(image_bytes))
        except Exception:
            return jsonify({'error': 'Imagem inválida.'}), 400

        face_locations = face_recognition.face_locations(img)
        if len(face_locations) != 1:
            return jsonify({'error': 'A imagem deve conter exatamente uma face.'}), 400

        encodings = face_recognition.face_encodings(img, face_locations)
        if not encodings:
            return jsonify({'error': 'Não foi possível gerar encoding da face.'}), 400
        face_encoding = encodings[0].tolist()

        file_uuid = str(uuid.uuid4())
        filename = salvaIMG(image_bytes, image_file.filename, file_uuid)

        update_fields.append("image_filename = ?")
        params.append(filename)
        update_fields.append("face_encoding = ?")
        params.append(json.dumps(face_encoding))

    params.append(user_uuid)
    query = "UPDATE pessoas SET " + ", ".join(update_fields) + " WHERE uuid = ?"

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

    return jsonify({'message': 'Usuário atualizado com sucesso.'}), 200



# EndPoint /imagens: Retorna todos os registros para controle
@app.route('/imagens', methods=['GET'])
def imagens():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT uuid, nome, telefone, endereco, ativo, image_filename FROM pessoas')
    rows = c.fetchall()
    conn.close()

    data = []
    for row in rows:
        data.append({
            'uuid': row[0],
            'nome': row[1],
            'telefone': row[2],
            'endereco': row[3],
            'ativo': row[4],
            'image_url': request.host_url + 'img/' + row[5]
        })
    return jsonify(data), 200

# EndPoint /compara: Recebe uma imagem, gera encoding e compara com toda a base
@app.route('/compara', methods=['POST'])
def compara():
    image_file = request.files.get('image')
    if not image_file:
        return jsonify({'error': 'Imagem é obrigatória.'}), 400
    try:
        image_bytes = image_file.read()
        img = face_recognition.load_image_file(BytesIO(image_bytes))
    except Exception:
        return jsonify({'error': 'Imagem inválida.'}), 400

    face_locations = face_recognition.face_locations(img)
    if len(face_locations) == 0:
        return jsonify({'error': 'Nenhuma face encontrada na imagem.'}), 400

    face_encodings = face_recognition.face_encodings(img, face_locations)
    results = []

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        SELECT uuid, nome, telefone, endereco, ativo, image_filename, face_encoding
        FROM pessoas
        WHERE ativo = 1
    ''')
    rows = c.fetchall()
    conn.close()

    threshold = 0.6
    pil_img = Image.fromarray(img)  # Prepara a imagem para realizar crop

    for i, (face_encoding, face_location) in enumerate(zip(face_encodings, face_locations)):
        top, right, bottom, left = face_location
        cropped_face = pil_img.crop((left, top, right, bottom))
        buffered = BytesIO()
        cropped_face.save(buffered, format="JPEG")
        face_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        face_data_url = "data:image/jpeg;base64," + face_b64

        best_match = None
        lowest_distance = None
        for row in rows:
            stored_encoding = np.array(json.loads(row[6]))
            distance = np.linalg.norm(stored_encoding - face_encoding)
            if distance < threshold:
                if lowest_distance is None or distance < lowest_distance:
                    lowest_distance = distance
                    best_match = row

        if best_match:
            results.append({
                'face_index': i,
                'uuid': best_match[0],
                'nome': best_match[1],
                'telefone': best_match[2],
                'endereco': best_match[3],
                'ativo': best_match[4],
                'image_url': request.host_url + 'img/' + best_match[5],
                'uploaded_face': face_data_url
            })
        else:
            results.append({
                'face_index': i,
                'match': None,
                'uploaded_face': face_data_url
            })

    return jsonify(results), 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
