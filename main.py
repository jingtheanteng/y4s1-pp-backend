from flask import Flask, request, send_from_directory
from flask_cors import CORS
import sqlite3
import requests
import os
from werkzeug.utils import secure_filename
import time
import uuid
from datetime import datetime, timedelta

# Add after app creation
app = Flask(__name__)
CORS(app)

# Add upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def home():
    return 'Home', 200

def _drop_table(cursor, table_name):
    cr = cursor
    cr.execute(f'''
        SELECT max(id) FROM {table_name}
        ORDER BY id ASC;
    ''')

def get_sequence_id(cursor, table_name):
    cr = cursor
    cr.execute(f'''
        SELECT max(id) FROM {table_name}
        ORDER BY id ASC;
    ''')
    last_id = cr.fetchall()[0]
    id = last_id[0]+1 if last_id[0] else 0 + 1
    return id

def check_exist(cursor, table_name, field, value):
    cr = cursor
    cr.execute(f'''
        SELECT {field} FROM {table_name}
        WHERE {field} = '{value}';
    ''')
    exists = cr.fetchall()
    if len(exists):
        return True
    return False


@app.route('/user')
def users():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('SELECT * FROM user')
    users = [{
        'id': row[0],
        'name': row[1],
        'bio': row[2],
        'email': row[3],
        'address': row[4],
        'phone': row[5],
        'password': row[6]
    } for row in cr.fetchall()]
    conn.commit()
    conn.close()
    return {
        'status': 'success',
        'data': users,
        'message': 'Users retrieved successfully'
    }, 200


@app.route('/user/create', methods=['POST'])
def create_users():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    id = get_sequence_id(cr, table_name="user")
    check_name = check_exist(cr, "user", "name", data['name'])
    check_email = check_exist(cr, "user", "email", data['email'])
    
    if check_email or check_name:
        return {'status': False, 'message': "Email or Username already exist."}
    
    # Store the password directly
    password = data.get('password')
    if not password:
        return {'status': False, 'message': "Password is required."}
    
    cr.execute('''
        INSERT INTO user (id, name, bio, email, address, phone, password)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (id, data['name'], data.get('bio'), data['email'], 
          data.get('address'), data.get('phone'), password))
    conn.commit()
    conn.close()
    
    return {'status': True, 'message': "Registered Successfully."}

@app.route('/user/authenticate', methods=['POST'])
def login_users():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    # Validate input
    if not email or not password:
        return {'status': False, 'message': "Email and password are required"}, 400
    
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()

    try:
        # Use parameterized query to prevent SQL injection
        cr.execute('SELECT * FROM user WHERE email = ?', (email,))
        queried_data = cr.fetchone()

        print('queried_data', queried_data)
        
        # Check if user exists
        if not queried_data:
            return {'status': False, 'message': "Invalid email or password"}, 401
        
        # Verify password directly
        stored_password = queried_data[6]  # Assuming password is at index 6
        
        if password != stored_password:
            return {'status': False, 'message': "Invalid email or password123"}, 401
        
        # Create user object
        user = {
            'id': queried_data[0], 
            'name': queried_data[1], 
            'bio': queried_data[2],
            'email': queried_data[3],
            'address': queried_data[4],
            'phone': queried_data[5]
        }
        
        # Create a session
        token = str(uuid.uuid4())
        created_at = datetime.now()
        expired_at = created_at + timedelta(days=30)
        
        cr.execute('''
            INSERT INTO session (user_id, token, created_at, expired_at)
            VALUES (?, ?, ?, ?)
        ''', (user['id'], token, created_at.isoformat(), expired_at.isoformat()))
        
        conn.commit()
        
        # Return user data and session token
        return {
            'status': True, 
            'message': "Login was successful", 
            'user': user,
            'session': {
                'token': token,
                'expired_at': expired_at.isoformat()
            }
        }
    except Exception as e:
        return {'status': False, 'message': f"Error: {str(e)}"}, 500
    finally:
        conn.close()

@app.route('/user/update-profile', methods=['POST'])
def update_profile():
    try:
        data = request.get_json()
        
        conn = sqlite3.connect('data.db')
        cr = conn.cursor()
        
        email = data.get('email')
        name = data.get('name')
        bio = data.get('bio')
        address = data.get('address')
        phone = data.get('phone')
        
        # First check if user exists
        cr.execute('SELECT * FROM user WHERE email = ?', (email,))
        user = cr.fetchone()
        if not user:
            return {'status': False, 'message': 'User not found'}
        
        # Update query with explicit column names
        update_query = '''
            UPDATE user 
            SET name = ?,
                bio = ?,
                address = ?,
                phone = ?
            WHERE email = ?
        '''
        
        cr.execute(update_query, (name, bio, address, phone, email))
        conn.commit()
        
        # Get updated user data
        cr.execute('SELECT * FROM user WHERE email = ?', (email,))
        user_data = cr.fetchone()
        
        if user_data:
            user = {
                'id': user_data[0],
                'name': user_data[1],
                'bio': user_data[2],
                'email': user_data[3],
                'address': user_data[4],
                'phone': user_data[5]
            }
            return {
                'status': True,
                'message': 'Profile updated successfully',
                'user': user
            }
        else:
            return {'status': False, 'message': 'Failed to update profile'}
            
    except Exception as e:
        print("Error:", str(e))  # Debug print
        return {'status': False, 'message': f'Error: {str(e)}'}
    finally:
        conn.close()

@app.route('/user/<int:id>', methods=['DELETE'])
def delete_user(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # First check if user exists
        cr.execute('SELECT id FROM user WHERE id = ?', (id,))
        if not cr.fetchone():
            return {'status': False, 'message': 'User not found'}, 404
            
        # Delete the user
        cr.execute('DELETE FROM user WHERE id = ?', (id,))
        conn.commit()
        
        return {'status': True, 'message': 'User deleted successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

# Faculty CRUD Operations
@app.route('/faculty', methods=['GET'])
def get_faculties():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('SELECT * FROM faculty')
    faculties = [{
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'created_at': row[3]
    } for row in cr.fetchall()]
    conn.close()
    return {
        'status': True,
        'data': faculties,
        'message': 'Faculties retrieved successfully'
    }

@app.route('/faculty/<int:id>', methods=['GET'])
def get_faculty(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('SELECT * FROM faculty WHERE id = ?', (id,))
    row = cr.fetchone()
    conn.close()
    
    if row:
        faculty = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'created_at': row[3]
        }
        return {'status': True, 'data': faculty}
    return {'status': False, 'message': 'Faculty not found'}, 404

@app.route('/faculty', methods=['POST'])
def create_faculty():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            INSERT INTO faculty (name, description)
            VALUES (?, ?)
        ''', (data['name'], data.get('description')))
        conn.commit()
        return {'status': True, 'message': 'Faculty created successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/faculty/<int:id>', methods=['PUT'])
def update_faculty(id):
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            UPDATE faculty 
            SET name = ?, description = ?
            WHERE id = ?
        ''', (data['name'], data.get('description'), id))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Faculty updated successfully'}
        return {'status': False, 'message': 'Faculty not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/faculty/<int:id>', methods=['DELETE'])
def delete_faculty(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if faculty has departments
        cr.execute('SELECT COUNT(*) FROM department WHERE faculty_id = ?', (id,))
        if cr.fetchone()[0] > 0:
            return {'status': False, 'message': 'Cannot delete faculty with existing departments'}, 400
            
        cr.execute('DELETE FROM faculty WHERE id = ?', (id,))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Faculty deleted successfully'}
        return {'status': False, 'message': 'Faculty not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

# Department CRUD Operations
@app.route('/department', methods=['GET'])
def get_departments():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('''
        SELECT d.*, f.name as faculty_name 
        FROM department d 
        LEFT JOIN faculty f ON d.faculty_id = f.id
    ''')
    departments = [{
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'faculty_id': row[3],
        'created_at': row[4],
        'faculty_name': row[5]
    } for row in cr.fetchall()]
    conn.close()
    return {
        'status': True,
        'data': departments,
        'message': 'Departments retrieved successfully'
    }

@app.route('/department/<int:id>', methods=['GET'])
def get_department(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('''
        SELECT d.*, f.name as faculty_name 
        FROM department d 
        LEFT JOIN faculty f ON d.faculty_id = f.id 
        WHERE d.id = ?
    ''', (id,))
    row = cr.fetchone()
    conn.close()
    
    if row:
        department = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'faculty_id': row[3],
            'created_at': row[4],
            'faculty_name': row[5]
        }
        return {'status': True, 'data': department}
    return {'status': False, 'message': 'Department not found'}, 404

@app.route('/department', methods=['POST'])
def create_department():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Verify faculty exists
        if 'faculty_id' in data:
            cr.execute('SELECT id FROM faculty WHERE id = ?', (data['faculty_id'],))
            if not cr.fetchone():
                return {'status': False, 'message': 'Faculty not found'}, 404
        
        cr.execute('''
            INSERT INTO department (name, description, faculty_id)
            VALUES (?, ?, ?)
        ''', (data['name'], data.get('description'), data.get('faculty_id')))
        conn.commit()
        return {'status': True, 'message': 'Department created successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/department/<int:id>', methods=['PUT'])
def update_department(id):
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Verify faculty exists if faculty_id is provided
        if 'faculty_id' in data:
            cr.execute('SELECT id FROM faculty WHERE id = ?', (data['faculty_id'],))
            if not cr.fetchone():
                return {'status': False, 'message': 'Faculty not found'}, 404
        
        cr.execute('''
            UPDATE department 
            SET name = ?, description = ?, faculty_id = ?
            WHERE id = ?
        ''', (data['name'], data.get('description'), data.get('faculty_id'), id))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Department updated successfully'}
        return {'status': False, 'message': 'Department not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/department/<int:id>', methods=['DELETE'])
def delete_department(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('DELETE FROM department WHERE id = ?', (id,))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Department deleted successfully'}
        return {'status': False, 'message': 'Department not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/department/pin', methods=['POST'])
def pin_department():
    data = request.get_json()
    user_id = data.get('user_id')
    department_id = data.get('department_id')
    
    if not user_id or not department_id:
        return {'status': False, 'message': 'User ID and Department ID are required'}, 400
    
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if pin already exists
        cr.execute('''
            SELECT id FROM department_pin 
            WHERE user_id = ? AND department_id = ?
        ''', (user_id, department_id))
        
        existing_pin = cr.fetchone()
        
        if existing_pin:
            # Unpin the department
            cr.execute('''
                DELETE FROM department_pin 
                WHERE user_id = ? AND department_id = ?
            ''', (user_id, department_id))
            message = 'Department unpinned successfully'
        else:
            # Pin the department
            cr.execute('''
                INSERT INTO department_pin (user_id, department_id)
                VALUES (?, ?)
            ''', (user_id, department_id))
            message = 'Department pinned successfully'
            
        conn.commit()
        return {'status': True, 'message': message}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/department/pinned/<int:user_id>', methods=['GET'])
def get_pinned_departments(user_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            SELECT d.*, f.name as faculty_name 
            FROM department d
            JOIN department_pin dp ON d.id = dp.department_id
            LEFT JOIN faculty f ON d.faculty_id = f.id
            WHERE dp.user_id = ?
        ''', (user_id,))
        
        departments = [{
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'faculty_id': row[3],
            'created_at': row[4],
            'faculty_name': row[5]
        } for row in cr.fetchall()]
        
        return {
            'status': True,
            'data': departments,
            'message': 'Pinned departments retrieved successfully'
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

# Category CRUD Operations
@app.route('/category', methods=['GET'])
def get_categories():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('SELECT * FROM category')
    categories = [{
        'id': row[0],
        'name': row[1],
        'created_at': row[2]
    } for row in cr.fetchall()]
    conn.close()
    return {
        'status': True,
        'data': categories,
        'message': 'Categories retrieved successfully'
    }

@app.route('/category', methods=['POST'])
def create_category():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('INSERT INTO category (name) VALUES (?)', (data['name'],))
        conn.commit()
        return {'status': True, 'message': 'Category created successfully'}
    except sqlite3.IntegrityError:
        return {'status': False, 'message': 'Category name must be unique'}, 400
    finally:
        conn.close()

@app.route('/category/<int:id>', methods=['PUT'])
def update_category(id):
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('UPDATE category SET name = ? WHERE id = ?', (data['name'], id))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Category updated successfully'}
        return {'status': False, 'message': 'Category not found'}, 404
    except sqlite3.IntegrityError:
        return {'status': False, 'message': 'Category name must be unique'}, 400
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/category/<int:id>', methods=['DELETE'])
def delete_category(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if category is used in any posts
        cr.execute('SELECT COUNT(*) FROM post WHERE category_id = ?', (id,))
        if cr.fetchone()[0] > 0:
            return {'status': False, 'message': 'Cannot delete category that is being used by posts'}, 400
            
        cr.execute('DELETE FROM category WHERE id = ?', (id,))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Category deleted successfully'}
        return {'status': False, 'message': 'Category not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

# Post CRUD Operations
@app.route('/post', methods=['GET'])
def get_posts():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    # Add optional pagination parameters
    page = request.args.get('page', type=int)
    limit = request.args.get('limit', type=int)
    
    # Add filters for category_id, department_id, and owner_id
    category_id = request.args.get('category_id')
    department_id = request.args.get('department_id')
    owner_id = request.args.get('owner_id')
    sort_by = request.args.get('sort_by', 'created_at')  # Default sort by created_at
    sort_order = request.args.get('sort_order', 'DESC')  # Default sort order
    
    query = '''
        SELECT p.*, 
               u.name as owner_name,
               c.name as category_name,
               d.name as department_name,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.id) as comment_count
        FROM post p
        LEFT JOIN user u ON p.owner_id = u.id
        LEFT JOIN category c ON p.category_id = c.id
        LEFT JOIN department d ON p.department_id = d.id
        WHERE 1=1
    '''
    params = []
    
    # Add WHERE clauses if filters are provided
    if category_id:
        query += ' AND p.category_id = ?'
        params.append(category_id)
    
    if department_id:
        query += ' AND p.department_id = ?'
        params.append(department_id)
    
    if owner_id:
        query += ' AND p.owner_id = ?'
        params.append(owner_id)
    
    # Get total count before applying limit
    count_query = f"SELECT COUNT(*) FROM ({query}) as subquery"
    cr.execute(count_query, params)
    total_posts = cr.fetchone()[0]
    
    # Add sorting
    if sort_by == 'likes':
        query += ' ORDER BY p.like_count'
    else:
        query += ' ORDER BY p.created_at'
    
    query += f' {sort_order}'
    
    # Add pagination only if both page and limit are provided
    if page is not None and limit is not None:
        offset = (page - 1) * limit
        query += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
    
    cr.execute(query, params)
    posts = [{
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'department_id': row[3],
        'category_id': row[4],
        'owner_id': row[5],
        'like_count': row[6],
        'created_at': row[7],
        'owner_name': row[8],
        'category_name': row[9],
        'department_name': row[10],
        'comment_count': row[11]
    } for row in cr.fetchall()]
    
    response = {
        'status': True,
        'data': posts,
        'message': 'Posts retrieved successfully'
    }
    
    # Add pagination info only if pagination was requested
    if page is not None and limit is not None:
        total_pages = (total_posts + limit - 1) // limit
        response['pagination'] = {
            'page': page,
            'per_page': limit,
            'total_posts': total_posts,
            'total_pages': total_pages
        }
    
    conn.close()
    return response

@app.route('/post/<int:id>', methods=['GET'])
def get_post(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    cr.execute('''
        SELECT p.*, 
               u.name as owner_name,
               c.name as category_name,
               d.name as department_name,
               (SELECT COUNT(*) FROM comment WHERE post_id = p.id) as comment_count
        FROM post p
        LEFT JOIN user u ON p.owner_id = u.id
        LEFT JOIN category c ON p.category_id = c.id
        LEFT JOIN department d ON p.department_id = d.id
        WHERE p.id = ?
    ''', (id,))
    row = cr.fetchone()
    conn.close()
    
    if row:
        post = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'department_id': row[3],
            'category_id': row[4],
            'owner_id': row[5],
            'like_count': row[6],
            'created_at': row[7],
            'owner_name': row[8],
            'category_name': row[9],
            'department_name': row[10],
            'comment_count': row[11]
        }
        return {'status': True, 'data': post}
    return {'status': False, 'message': 'Post not found'}, 404

@app.route('/post', methods=['POST'])
def create_post():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            INSERT INTO post (name, description, department_id, category_id, owner_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data.get('description'),
            data.get('department_id'),
            data.get('category_id'),
            data['owner_id']
        ))
        conn.commit()
        return {'status': True, 'message': 'Post created successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/post/<int:id>', methods=['PUT'])
def update_post(id):
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            UPDATE post 
            SET name = ?, description = ?, department_id = ?, category_id = ?
            WHERE id = ? AND owner_id = ?
        ''', (
            data['name'],
            data.get('description'),
            data.get('department_id'),
            data.get('category_id'),
            id,
            data['owner_id']
        ))
        conn.commit()
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Post updated successfully'}
        return {'status': False, 'message': 'Post not found or unauthorized'}, 404
    finally:
        conn.close()

@app.route('/post/<int:id>/like', methods=['POST'])
def like_post(id):
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return {'status': False, 'message': 'User ID is required'}, 400
        
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if user has already liked the post
        cr.execute('''
            SELECT id FROM post_like 
            WHERE post_id = ? AND user_id = ?
        ''', (id, user_id))
        
        existing_like = cr.fetchone()
        
        if existing_like:
            # Unlike the post
            cr.execute('''
                DELETE FROM post_like 
                WHERE post_id = ? AND user_id = ?
            ''', (id, user_id))
            cr.execute('''
                UPDATE post 
                SET like_count = like_count - 1 
                WHERE id = ?
            ''', (id,))
            message = 'Post unliked successfully'
        else:
            # Like the post
            cr.execute('''
                INSERT INTO post_like (post_id, user_id)
                VALUES (?, ?)
            ''', (id, user_id))
            cr.execute('''
                UPDATE post 
                SET like_count = like_count + 1 
                WHERE id = ?
            ''', (id,))
            message = 'Post liked successfully'
            
        conn.commit()
        return {'status': True, 'message': message}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

# Comment CRUD Operations
@app.route('/comment', methods=['GET'])
def get_comments():
    post_id = request.args.get('post_id')
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    query = '''
        SELECT c.*, u.name as owner_name
        FROM comment c
        LEFT JOIN user u ON c.owner_id = u.id
    '''
    params = []
    
    if post_id:
        query += ' WHERE c.post_id = ?'
        params.append(post_id)
    
    query += ' ORDER BY c.created_at ASC'
    
    cr.execute(query, params)
    comments = [{
        'id': row[0],
        'name': row[1],
        'like_count': row[2],
        'owner_id': row[3],
        'post_id': row[4],
        'parent_comment_id': row[5],
        'created_at': row[6],
        'owner_name': row[7],
        'replies': []
    } for row in cr.fetchall()]

    # Fetch replies for each comment
    for comment in comments:
        cr.execute('''
            SELECT c.*, u.name as owner_name
            FROM comment c
            LEFT JOIN user u ON c.owner_id = u.id
            WHERE c.parent_comment_id = ?
            ORDER BY c.created_at ASC
        ''', (comment['id'],))
        
        comment['replies'] = [{
            'id': row[0],
            'name': row[1],
            'like_count': row[2],
            'owner_id': row[3],
            'post_id': row[4],
            'parent_comment_id': row[5],
            'created_at': row[6],
            'owner_name': row[7]
        } for row in cr.fetchall()]

    conn.close()
    return {
        'status': True,
        'data': comments,
        'message': 'Comments retrieved successfully'
    }

@app.route('/comment', methods=['POST'])
def create_comment():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Validate required fields
        if not data.get('name'):
            return {'status': False, 'message': 'Comment text is required'}, 400
        if not data.get('owner_id'):
            return {'status': False, 'message': 'User ID is required'}, 400
        if not data.get('post_id'):
            return {'status': False, 'message': 'Post ID is required'}, 400
            
        # If parent_comment_id is provided, verify it exists
        parent_id = data.get('parent_comment_id')
        if parent_id:
            cr.execute('SELECT id FROM comment WHERE id = ?', (parent_id,))
            if not cr.fetchone():
                return {'status': False, 'message': 'Parent comment not found'}, 404

        cr.execute('''
            INSERT INTO comment (name, owner_id, post_id, parent_comment_id)
            VALUES (?, ?, ?, ?)
        ''', (
            data['name'],
            data['owner_id'],
            data['post_id'],
            parent_id
        ))
        conn.commit()
        
        # Get the created comment
        comment_id = cr.lastrowid
        cr.execute('''
            SELECT c.*, u.name as owner_name
            FROM comment c
            LEFT JOIN user u ON c.owner_id = u.id
            WHERE c.id = ?
        ''', (comment_id,))
        row = cr.fetchone()
        
        return {
            'status': True,
            'message': 'Comment created successfully',
            'data': {
                'id': row[0],
                'name': row[1],
                'like_count': row[2],
                'owner_id': row[3],
                'post_id': row[4],
                'parent_comment_id': row[5],
                'created_at': row[6],
                'owner_name': row[7]
            }
        }
    except Exception as e:
        print('Error creating comment:', str(e))  # Add debug logging
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/comment/<int:id>/like', methods=['POST'])
def like_comment(id):
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return {'status': False, 'message': 'User ID is required'}, 400
        
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if user has already liked the comment
        cr.execute('''
            SELECT id FROM comment_like 
            WHERE comment_id = ? AND user_id = ?
        ''', (id, user_id))
        
        existing_like = cr.fetchone()
        
        if existing_like:
            # Unlike the comment
            cr.execute('''
                DELETE FROM comment_like 
                WHERE comment_id = ? AND user_id = ?
            ''', (id, user_id))
            cr.execute('''
                UPDATE comment 
                SET like_count = like_count - 1 
                WHERE id = ?
            ''', (id,))
            message = 'Comment unliked successfully'
        else:
            # Like the comment
            cr.execute('''
                INSERT INTO comment_like (comment_id, user_id)
                VALUES (?, ?)
            ''', (id, user_id))
            cr.execute('''
                UPDATE comment 
                SET like_count = like_count + 1 
                WHERE id = ?
            ''', (id,))
            message = 'Comment liked successfully'
            
        conn.commit()
        return {'status': True, 'message': message}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/comment/<int:id>', methods=['DELETE'])
def delete_comment(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # First check if comment exists
        cr.execute('SELECT id FROM comment WHERE id = ?', (id,))
        if not cr.fetchone():
            return {'status': False, 'message': 'Comment not found'}, 404
            
        # Delete the comment
        cr.execute('DELETE FROM comment WHERE id = ?', (id,))
        conn.commit()
        
        return {'status': True, 'message': 'Comment deleted successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/comment/<int:id>/likes', methods=['GET'])
def check_comment_like(id):
    user_id = request.args.get('user_id')
    
    if not user_id:
        return {'status': False, 'message': 'User ID is required'}, 400
        
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if user has liked the comment
        cr.execute('''
            SELECT id FROM comment_like 
            WHERE comment_id = ? AND user_id = ?
        ''', (id, user_id))
        
        has_liked = cr.fetchone() is not None
        
        return {
            'status': True,
            'data': {
                'has_liked': has_liked
            }
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/post/<int:id>', methods=['DELETE'])
def delete_post(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # First check if post exists
        cr.execute('SELECT id FROM post WHERE id = ?', (id,))
        if not cr.fetchone():
            return {'status': False, 'message': 'Post not found'}, 404
            
        # Delete associated comments first (due to foreign key constraint)
        cr.execute('DELETE FROM comment WHERE post_id = ?', (id,))
        
        # Delete associated likes
        cr.execute('DELETE FROM post_like WHERE post_id = ?', (id,))
        
        # Delete the post
        cr.execute('DELETE FROM post WHERE id = ?', (id,))
        conn.commit()
        
        return {'status': True, 'message': 'Post deleted successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/post/<int:id>/likes', methods=['GET'])
def check_post_like(id):
    user_id = request.args.get('user_id')
    
    if not user_id:
        return {'status': False, 'message': 'User ID is required'}, 400
        
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if user has liked the post
        cr.execute('''
            SELECT id FROM post_like 
            WHERE post_id = ? AND user_id = ?
        ''', (id, user_id))
        
        has_liked = cr.fetchone() is not None
        
        return {
            'status': True,
            'data': {
                'has_liked': has_liked
            }
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/session/create', methods=['POST'])
def create_session():
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return {'status': False, 'message': 'User ID is required'}, 400
    
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if user exists
        cr.execute('SELECT id FROM user WHERE id = ?', (user_id,))
        if not cr.fetchone():
            return {'status': False, 'message': 'User not found'}, 404
        
        # Generate token
        token = str(uuid.uuid4())
        
        # Set expiration date (1 month from now)
        created_at = datetime.now()
        expired_at = created_at + timedelta(days=30)
        
        # Insert session into database
        cr.execute('''
            INSERT INTO session (user_id, token, created_at, expired_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, token, created_at.isoformat(), expired_at.isoformat()))
        
        conn.commit()
        
        return {
            'status': True,
            'message': 'Session created successfully',
            'data': {
                'token': token,
                'user_id': user_id,
                'created_at': created_at.isoformat(),
                'expired_at': expired_at.isoformat()
            }
        }
    except Exception as e:
        return {'status': False, 'message': f'Error: {str(e)}'}, 500
    finally:
        conn.close()

@app.route('/session/validate', methods=['POST'])
def validate_session():
    data = request.get_json()
    token = data.get('token')
    
    if not token:
        return {'status': False, 'message': 'Token is required'}, 400
    
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Check if session exists
        cr.execute('''
            SELECT id, user_id, created_at, expired_at 
            FROM session 
            WHERE token = ?
        ''', (token,))
        
        session = cr.fetchone()
        
        if not session:
            return {'status': False, 'message': 'Session not found'}, 404
        
        # Parse dates
        expired_at = datetime.fromisoformat(session[3])
        now = datetime.now()
        
        # Check if session is expired
        is_valid = now < expired_at
        
        return {
            'status': True,
            'data': {
                'valid': is_valid,
                'expired': not is_valid,
                'user_id': session[1],
                'expired_at': session[3]
            }
        }
    except Exception as e:
        return {'status': False, 'message': f'Error: {str(e)}'}, 500
    finally:
        conn.close()

if __name__ == '__main__':
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    
    # Drop existing table if it exists
    # cur.execute('DROP TABLE IF EXISTS session')
    
    cur.execute('DROP TABLE IF EXISTS comment_like')
    cur.execute('DROP TABLE IF EXISTS comment')
    
    cur.execute('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        bio TEXT,
        email TEXT,
        address TEXT,
        phone TEXT,
        password TEXT
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS faculty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS department (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        faculty_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (faculty_id) REFERENCES faculty (id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS category (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS post (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        department_id INTEGER,
        category_id INTEGER,
        owner_id INTEGER,
        like_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES department (id),
        FOREIGN KEY (category_id) REFERENCES category (id),
        FOREIGN KEY (owner_id) REFERENCES user (id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS comment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        like_count INTEGER DEFAULT 0,
        owner_id INTEGER,
        post_id INTEGER,
        parent_comment_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_id) REFERENCES user (id),
        FOREIGN KEY (post_id) REFERENCES post (id),
        FOREIGN KEY (parent_comment_id) REFERENCES comment (id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS session (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        token TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS post_like (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES post (id),
        FOREIGN KEY (user_id) REFERENCES user (id),
        UNIQUE(post_id, user_id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS comment_like (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comment_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (comment_id) REFERENCES comment (id),
        FOREIGN KEY (user_id) REFERENCES user (id),
        UNIQUE(comment_id, user_id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS department_pin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        department_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id),
        FOREIGN KEY (department_id) REFERENCES department (id),
        UNIQUE(user_id, department_id)
    )''')
    conn.commit()
    conn.close()
    app.run(host='0.0.0.0', port=5001, debug=True)
