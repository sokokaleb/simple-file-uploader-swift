from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_bootstrap import Bootstrap
from flask_dotenv import DotEnv
from functools import wraps
import swiftclient
from swiftclient.exceptions import ClientException

app = Flask(__name__)
Bootstrap(app)
env = DotEnv()
env.init_app(app)
env.eval(keys={
    'DEBUG': int,
    'MAX_CONTENT_LENGTH': int
});

class Bucket(object):
    def __init__(self, name=None, size=None, file_count=None,
                 delete_link=None, get_link=None):
        self.name = name
        self.size = size
        self.file_count = file_count
        self.delete_link = delete_link
        self.get_link = get_link

class Object(object):
    def __init__(self, name=None, size=None, delete_link=None, get_link=None,
                 last_modified=None):
        self.name = name
        self.size = size
        self.delete_link = delete_link
        self.get_link = get_link
        self.last_modified = last_modified

def attach_conn(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = swiftclient.Connection(user=app.config['SWIFT_USER'],
                                      key=app.config['SWIFT_KEY'],
                                      authurl=app.config['AUTH_URL'])
        try:
            return f(conn=conn, *args, **kwargs)
        except ClientException, e:
            return e.http_reason, e.http_status
    return decorated_function

# lists all buckets
@app.route('/', methods=['GET'])
@attach_conn
def get_all_buckets(conn):
    buckets = conn.get_account()[1]
    rendered_buckets = []
    for bucket in buckets:
        rendered_bucket = Bucket(name=bucket['name'],
                                 size=bucket['bytes'],
                                 file_count=bucket['count'],
                                 delete_link=url_for('delete_bucket',
                                                      bucket_name=bucket['name']),
                                 get_link=url_for('get_all_objects',
                                                  bucket_name=bucket['name']))
        rendered_buckets.append(rendered_bucket)
    return render_template('index.html',
                           buckets=rendered_buckets,
                           create_bucket_link=url_for('create_bucket'))
    # return jsonify(buckets)

# lists all objects in a bucket
@app.route('/<bucket_name>', methods=['GET'])
@attach_conn
def get_all_objects(conn, bucket_name):
    objects = conn.get_container(container=bucket_name)[1]
    rendered_objects = []
    for object in objects:
        rendered_object = Object(name=object['name'],
                                 size=object['bytes'],
                                 last_modified=object['last_modified'],
                                 delete_link=url_for('delete_object',
                                                     bucket_name=bucket_name,
                                                     object_name=object['name']),
                                 get_link=url_for('get_object',
                                                  bucket_name=bucket_name,
                                                  object_name=object['name']))
        rendered_objects.append(rendered_object)
    buckets = conn.get_account()[1]
    bucket_names = []
    for bucket in buckets:
        if bucket['name'] != bucket_name:
            bucket_names.append(bucket['name'])
    return render_template('bucket.html',
                           bucket_name=bucket_name,
                           bucket_names=bucket_names,
                           objects=rendered_objects,
                           create_object_link=url_for('create_object'),
                           copy_object_link=url_for('copy_object'))

# delete a bucket
@app.route('/delete-bucket/<bucket_name>', methods=['GET'])
@attach_conn
def delete_bucket(conn, bucket_name):
    conn.delete_container(bucket_name)
    return redirect(url_for('get_all_buckets'))

# create a bucket
@app.route('/create-bucket', methods=['POST'])
@attach_conn
def create_bucket(conn):
    bucket_name = request.form.get('bucket')
    conn.put_container(bucket_name)
    return redirect(url_for('get_all_buckets'))

# download a file
@app.route('/<bucket_name>/<object_name>', methods=['GET'])
@attach_conn
def get_object(conn, bucket_name, object_name):
    object = conn.get_object(bucket_name, object_name)[1]
    return object, 200, \
           {'Content-Disposition': 'attachment; filename=%s' % object_name}

# delete object
@app.route('/delete-object/<bucket_name>/<object_name>', methods=['GET'])
@attach_conn
def delete_object(conn, bucket_name, object_name):
    conn.delete_object(bucket_name, object_name)
    return redirect(url_for('get_all_objects', bucket_name=bucket_name))

# create object
@app.route('/create-object', methods=['POST'])
@attach_conn
def create_object(conn):
    bucket_name = request.form.get('bucket')
    object_name = request.form.get('object')
    if 'up_object' not in request.files \
            or request.files['up_object'].filename == '':
        return 'No file selected', 400
    uploaded_file = request.files['up_object']
    if object_name == '' or type(object_name) == 'undefined':
        object_name = uploaded_file.filename
    buf = uploaded_file.read()
    conn.put_object(bucket_name, object_name, buf)
    return redirect(url_for('get_all_objects', bucket_name=bucket_name))

# copy object between buckets
@app.route('/copy-object', methods=['POST'])
@attach_conn
def copy_object(conn):
    source_bucket = request.form.get('source_bucket')
    source_object = request.form.get('source_object')
    destination_bucket = request.form.get('destination_bucket')
    destination_object = request.form.get('destination_object')
    if type(destination_object) == 'undefined' or destination_object == '':
        destination_object = source_object
    destination = '/{}/{}'.format(destination_bucket, destination_object)
    conn.copy_object(source_bucket, source_object, destination=destination)
    return redirect(url_for('get_all_objects', bucket_name=source_bucket))

if __name__ == '__main__':
    app.run(host=app.config['HOST'],
            port=app.config['PORT'],
            debug=app.config['DEBUG'])
