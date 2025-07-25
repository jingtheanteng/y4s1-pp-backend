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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'xlsx', 'xls', 'csv', 'doc', 'docx', 'txt'}

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
        'password': row[6],
        'city': row[7],
        'department': row[8],
        'points': row[9] if len(row) > 9 else 0,
        'banned': row[10] if len(row) > 10 else False,
        'profile_picture': row[11] if len(row) > 11 else None,
        'admin': row[12] if len(row) > 12 else False  # Add admin field
    } for row in cr.fetchall()]
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
        INSERT INTO user (id, name, bio, email, address, phone, password, city, department)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (id, data['name'], data.get('bio'), data['email'], 
          data.get('address'), data.get('phone'), password,
          data.get('city'), data.get('department')))
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
        
        # Check if user is banned
        if queried_data[10]:  # banned field is at index 10
            return {'status': False, 'message': "This account has been banned"}, 403
        
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
            'phone': queried_data[5],
            'banned': queried_data[10],
            'profile_picture': queried_data[11] if len(queried_data) > 11 else None,
            'admin': queried_data[12] if len(queried_data) > 12 else False  # Add admin field
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
        city = data.get('city')
        department = data.get('department')
        profile_picture = data.get('profile_picture')  # Add profile picture field
        admin = data.get('admin')
        
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
                phone = ?,
                city = ?,
                department = ?,
                profile_picture = ?,
                admin = ?
            WHERE email = ?
        '''
        
        cr.execute(update_query, (name, bio, address, phone, city, department, profile_picture, admin, email))
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
                'phone': user_data[5],
                'city': user_data[7],
                'department': user_data[8],
                'banned': user_data[10],
                'profile_picture': user_data[11] if len(user_data) > 11 else None,
                'admin': user_data[12] if len(user_data) > 12 else False  # Add profile picture to response
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
            
        # Delete associated notifications
        cr.execute('DELETE FROM notification WHERE user_id = ?', (id,))
        
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
               u.profile_picture as profile_picture,
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
    if sort_by == 'trending':
        # Sort by combined likes and comments
        query += ' ORDER BY (p.like_count + comment_count)'
    elif sort_by == 'likes':
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
        'profile_picture': row[9],
        'category_name': row[10],
        'department_name': row[11],
        'comment_count': row[12],
        'attachments': []  # Initialize empty attachments array
    } for row in cr.fetchall()]
    
    # If we have posts, get their attachments
    if posts:
        # Get all post IDs
        post_ids = [post['id'] for post in posts]
        placeholders = ','.join(['?' for _ in post_ids])
        
        # Get all attachments for these posts
        attachment_query = f'''
            SELECT post_id, id, file_name, file_path, file_type, file_size, created_at
            FROM attachment 
            WHERE post_id IN ({placeholders})
            ORDER BY post_id, created_at DESC
        '''
        cr.execute(attachment_query, post_ids)
        
        # Group attachments by post_id
        attachments_by_post = {}
        for attachment_row in cr.fetchall():
            post_id = attachment_row[0]
            if post_id not in attachments_by_post:
                attachments_by_post[post_id] = []
            
            attachments_by_post[post_id].append({
                'id': attachment_row[1],
                'file_name': attachment_row[2],
                'file_path': attachment_row[3],
                'file_type': attachment_row[4],
                'file_size': attachment_row[5],
                'created_at': attachment_row[6]
            })
        
        # Add attachments to each post
        for post in posts:
            post['attachments'] = attachments_by_post.get(post['id'], [])
    
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
    
    try:
        # Get post information
        cr.execute('''
            SELECT p.*, 
                   u.name as owner_name,
                   u.profile_picture as profile_picture,
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
        
        if not row:
            return {'status': False, 'message': 'Post not found'}, 404
            
        # Get attachments for the post
        cr.execute('''
            SELECT id, file_name, file_path, file_type, file_size, created_at
            FROM attachment 
            WHERE post_id = ?
            ORDER BY created_at DESC
        ''', (id,))
        
        attachments = [{
            'id': row[0],
            'file_name': row[1],
            'file_path': row[2],
            'file_type': row[3],
            'file_size': row[4],
            'created_at': row[5]
        } for row in cr.fetchall()]
        
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
            'profile_picture': row[9],
            'category_name': row[10],
            'department_name': row[11],
            'comment_count': row[12],
            'attachments': attachments  # Add attachments to the response
        }
        
        return {'status': True, 'data': post}
    except Exception as e:
        print('Error in get_post:', str(e))
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/post', methods=['POST'])
def create_post():
    try:
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description')
        department_id = request.form.get('department_id')
        category_id = request.form.get('category_id')
        owner_id = request.form.get('owner_id')
        
        # Validate required fields
        if not all([name, owner_id]):
            return {'status': False, 'message': 'Name and owner_id are required'}, 400
        
        conn = sqlite3.connect('data.db')
        cr = conn.cursor()
        
        try:
            # First check if user exists and get current points
            cr.execute('SELECT points FROM user WHERE id = ?', (owner_id,))
            user_result = cr.fetchone()
            if not user_result:
                return {'status': False, 'message': 'User not found'}, 404
                
            current_points = user_result[0] if user_result[0] is not None else 0
            
            # Insert the post
            cr.execute('''
                INSERT INTO post (name, description, department_id, category_id, owner_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                name,
                description,
                department_id,
                category_id,
                owner_id
            ))
            
            post_id = cr.lastrowid
            
            # Handle file attachments if any
            attachments = []
            if 'files' in request.files:
                files = request.files.getlist('files')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        # Generate unique filename
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid.uuid4()}_{filename}"
                        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                        
                        # Save file
                        file.save(file_path)
                        
                        # Get file size
                        file_size = os.path.getsize(file_path)
                        
                        # Save attachment info to database
                        cr.execute('''
                            INSERT INTO attachment (post_id, file_name, file_path, file_type, file_size)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (post_id, filename, unique_filename, file.content_type, file_size))
                        
                        attachments.append({
                            'id': cr.lastrowid,
                            'file_name': filename,
                            'file_path': unique_filename,
                            'file_type': file.content_type,
                            'file_size': file_size
                        })
            
            # Update user points (add 5 points)
            new_points = current_points + 5
            cr.execute('''
                UPDATE user 
                SET points = ? 
                WHERE id = ?
            ''', (new_points, owner_id))
            
            conn.commit()
            
            return {
                'status': True, 
                'message': 'Post created successfully',
                'data': {
                    'post_id': post_id,
                    'points': new_points,
                    'attachments': attachments
                }
            }
        except Exception as e:
            print('Error in create_post:', str(e))
            return {'status': False, 'message': str(e)}, 400
        finally:
            conn.close()
            
    except Exception as e:
        print('Error in create_post:', str(e))
        return {'status': False, 'message': str(e)}, 400

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
        SELECT c.*, u.name as owner_name, u.profile_picture as profile_picture
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
        'profile_picture': row[8],
        'replies': []
    } for row in cr.fetchall()]

    # Fetch replies for each comment
    for comment in comments:
        cr.execute('''
            SELECT c.*, u.name as owner_name, u.profile_picture as profile_picture
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
            'owner_name': row[7],
            'profile_picture': row[8]
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

        # Get post owner's ID
        cr.execute('SELECT owner_id FROM post WHERE id = ?', (data['post_id'],))
        post_owner = cr.fetchone()
        if not post_owner:
            return {'status': False, 'message': 'Post not found'}, 404

        cr.execute('''
            INSERT INTO comment (name, owner_id, post_id, parent_comment_id)
            VALUES (?, ?, ?, ?)
        ''', (
            data['name'],
            data['owner_id'],
            data['post_id'],
            parent_id
        ))
        
        # Add 1 point for creating a comment
        cr.execute('''
            UPDATE user 
            SET points = points + 1 
            WHERE id = ?
        ''', (data['owner_id'],))
        
        # Get the created comment ID
        comment_id = cr.lastrowid

        # Create notification for post owner if commenter is not the post owner
        if post_owner[0] != data['owner_id']:
            cr.execute('''
                INSERT INTO notification (user_id, post_id, comment_id, commenter_id)
                VALUES (?, ?, ?, ?)
            ''', (post_owner[0], data['post_id'], comment_id, data['owner_id']))
        
        # If this is a reply to a comment, create notification for the original comment owner
        if parent_id:
            # Get the original comment owner's ID
            cr.execute('SELECT owner_id FROM comment WHERE id = ?', (parent_id,))
            original_comment_owner = cr.fetchone()
            if original_comment_owner and original_comment_owner[0] != data['owner_id']:
                cr.execute('''
                    INSERT INTO notification (user_id, post_id, comment_id, commenter_id)
                    VALUES (?, ?, ?, ?)
                ''', (original_comment_owner[0], data['post_id'], comment_id, data['owner_id']))
        
        conn.commit()
        
        # Get the created comment
        cr.execute('''
            SELECT c.*, u.name as owner_name, u.profile_picture as profile_picture
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
                'owner_name': row[7],
                'profile_picture': row[8]
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
        # Check if session exists and get user info
        cr.execute('''
            SELECT s.id, s.user_id, s.created_at, s.expired_at, u.banned
            FROM session s
            JOIN user u ON s.user_id = u.id
            WHERE s.token = ?
        ''', (token,))
        
        session = cr.fetchone()
        
        if not session:
            return {'status': False, 'message': 'Session not found'}, 404
        
        # Parse dates
        expired_at = datetime.fromisoformat(session[3])
        now = datetime.now()
        
        # Check if session is expired
        is_valid = now < expired_at
        
        # Check if user is banned
        is_banned = session[4]
        
        if is_banned:
            return {
                'status': False,
                'message': 'This account has been banned',
                'data': {
                    'valid': False,
                    'expired': False,
                    'banned': True,
                    'user_id': session[1],
                    'expired_at': session[3]
                }
            }
        
        return {
            'status': True,
            'data': {
                'valid': is_valid,
                'expired': not is_valid,
                'banned': False,
                'user_id': session[1],
                'expired_at': session[3]
            }
        }
    except Exception as e:
        return {'status': False, 'message': f'Error: {str(e)}'}, 500
    finally:
        conn.close()

@app.route('/department/popular', methods=['GET'])
def get_popular_departments():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Get departments with their post counts, ordered by post count
        cr.execute('''
            SELECT d.*, f.name as faculty_name, 
                   COUNT(p.id) as post_count
            FROM department d
            LEFT JOIN faculty f ON d.faculty_id = f.id
            LEFT JOIN post p ON d.id = p.department_id
            GROUP BY d.id
            ORDER BY post_count DESC
            LIMIT 5
        ''')
        
        departments = [{
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'faculty_id': row[3],
            'created_at': row[4],
            'faculty_name': row[5],
            'post_count': row[6]
        } for row in cr.fetchall()]
        
        return {
            'status': True,
            'data': departments,
            'message': 'Popular departments retrieved successfully'
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/notifications/<int:user_id>', methods=['GET'])
def get_notifications(user_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Get all notifications for the user
        cr.execute('''
            SELECT n.*, 
                   u.name as commenter_name,
                   p.name as post_name,
                   c.name as comment_text,
                   c.parent_comment_id as is_reply
            FROM notification n
            LEFT JOIN user u ON n.commenter_id = u.id
            LEFT JOIN post p ON n.post_id = p.id
            LEFT JOIN comment c ON n.comment_id = c.id
            WHERE n.user_id = ?
            ORDER BY n.created_at DESC
        ''', (user_id,))
        
        notifications = [{
            'id': row[0],
            'post_id': row[2],
            'comment_id': row[3],
            'commenter_id': row[4],
            'is_read': row[5],
            'created_at': row[6],
            'commenter_name': row[7],
            'post_name': row[8],
            'comment_text': row[9],
            'is_reply': row[10] is not None
        } for row in cr.fetchall()]
        
        return {
            'status': True,
            'data': notifications,
            'message': 'Notifications retrieved successfully'
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/notifications/<int:notification_id>/read', methods=['PUT'])
def mark_notification_read(notification_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            UPDATE notification 
            SET is_read = TRUE 
            WHERE id = ?
        ''', (notification_id,))
        
        conn.commit()
        
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Notification marked as read'}
        return {'status': False, 'message': 'Notification not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/notifications/<int:user_id>/clear', methods=['DELETE'])
def clear_all_notifications(user_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Delete all notifications for the user
        cr.execute('DELETE FROM notification WHERE user_id = ?', (user_id,))
        conn.commit()
        
        return {'status': True, 'message': 'All notifications cleared successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/reports', methods=['GET'])
def get_reports():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Get all reports with related information
        cr.execute('''
            SELECT r.*,
                   u1.name as reporter_name,
                   CASE 
                       WHEN r.type = 'post' THEN p.owner_id
                       WHEN r.type = 'comment' THEN c.owner_id
                   END as content_owner_id,
                   CASE 
                       WHEN r.type = 'post' THEN u2.name
                       WHEN r.type = 'comment' THEN u3.name
                   END as content_owner_name,
                   CASE 
                       WHEN r.type = 'post' THEN p.name
                       WHEN r.type = 'comment' THEN c.name
                   END as content,
                   p.name as post_name
            FROM report r
            LEFT JOIN user u1 ON r.reporter_id = u1.id
            LEFT JOIN post p ON r.post_id = p.id
            LEFT JOIN comment c ON r.comment_id = c.id
            LEFT JOIN user u2 ON p.owner_id = u2.id
            LEFT JOIN user u3 ON c.owner_id = u3.id
            ORDER BY r.created_at DESC
        ''')
        
        reports = [{
            'id': row[0],
            'type': row[1],
            'reason': row[2],
            'description': row[3],
            'post_id': row[4],
            'comment_id': row[5],
            'reporter_id': row[6],
            'status': row[7],
            'created_at': row[8],
            'reporter': row[9],
            'content_owner_id': row[10],
            'content_owner': row[11],
            'content': row[12],
            'post_name': row[13]
        } for row in cr.fetchall()]
        
        return {
            'status': True,
            'data': reports,
            'message': 'Reports retrieved successfully'
        }
    except Exception as e:
        print('Error fetching reports:', str(e))  # Add debug logging
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/report', methods=['POST'])
def create_report():
    data = request.get_json()
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Validate required fields
        required_fields = ['type', 'reason', 'reporter_id']
        for field in required_fields:
            if not data.get(field):
                return {'status': False, 'message': f'{field} is required'}, 400

        cr.execute('''
            INSERT INTO report (type, reason, description, post_id, comment_id, reporter_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['type'],
            data['reason'],
            data.get('description'),
            data.get('post_id'),
            data.get('comment_id'),
            data['reporter_id']
        ))
        
        conn.commit()
        return {'status': True, 'message': 'Report created successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/report/<int:id>/status', methods=['PUT'])
def update_report_status(id):
    data = request.get_json()
    new_status = data.get('status')
    
    if not new_status or new_status not in ['pending', 'resolved', 'rejected']:
        return {'status': False, 'message': 'Invalid status'}, 400
        
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            UPDATE report 
            SET status = ? 
            WHERE id = ?
        ''', (new_status, id))
        
        conn.commit()
        
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Report status updated successfully'}
        return {'status': False, 'message': 'Report not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/report/<int:id>', methods=['DELETE'])
def delete_report(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('DELETE FROM report WHERE id = ?', (id,))
        conn.commit()
        
        if cr.rowcount > 0:
            return {'status': True, 'message': 'Report deleted successfully'}
        return {'status': False, 'message': 'Report not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/admin/statistics', methods=['GET'])
def get_statistics():
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Get time filter from query params
        time_filter = request.args.get('time_filter', 'all')  # all, day, week, month, year
        
        # Base query for time filtering
        time_condition = ""
        if time_filter == 'day':
            time_condition = "AND created_at >= datetime('now', '-1 day')"
        elif time_filter == 'week':
            time_condition = "AND created_at >= datetime('now', '-7 days')"
        elif time_filter == 'month':
            time_condition = "AND created_at >= datetime('now', '-30 days')"
        elif time_filter == 'year':
            time_condition = "AND created_at >= datetime('now', '-365 days')"
        
        # Get total users
        cr.execute(f'SELECT COUNT(*) FROM user {time_condition}')
        total_users = cr.fetchone()[0]
        
        # Get total posts
        cr.execute(f'SELECT COUNT(*) FROM post {time_condition}')
        total_posts = cr.fetchone()[0]
        
        # Get total reports
        cr.execute(f'SELECT COUNT(*) FROM report {time_condition}')
        total_reports = cr.fetchone()[0]
        
        # Get reports by status
        cr.execute(f'''
            SELECT status, COUNT(*) as count 
            FROM report 
            {time_condition}
            GROUP BY status
        ''')
        reports_by_status = {row[0]: row[1] for row in cr.fetchall()}
        
        return {
            'status': True,
            'data': {
                'total_users': total_users,
                'total_posts': total_posts,
                'total_reports': total_reports,
                'reports_by_status': reports_by_status
            },
            'message': 'Statistics retrieved successfully'
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/user/ban/<int:id>', methods=['POST'])
def ban_user(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # First check if user exists
        cr.execute('SELECT id FROM user WHERE id = ?', (id,))
        if not cr.fetchone():
            return {'status': False, 'message': 'User not found'}, 404
            
        # Ban the user
        cr.execute('UPDATE user SET banned = TRUE WHERE id = ?', (id,))
        conn.commit()
        
        return {'status': True, 'message': 'User banned successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/user/unban/<int:id>', methods=['POST'])
def unban_user(id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # First check if user exists
        cr.execute('SELECT id FROM user WHERE id = ?', (id,))
        if not cr.fetchone():
            return {'status': False, 'message': 'User not found'}, 404
            
        # Unban the user
        cr.execute('UPDATE user SET banned = FALSE WHERE id = ?', (id,))
        conn.commit()
        
        return {'status': True, 'message': 'User unbanned successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/search', methods=['GET'])
def search_posts():
    query = request.args.get('q', '')
    if not query:
        return {'status': True, 'data': [], 'message': 'No search query provided'}

    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Search in posts by title and description
        cr.execute('''
            SELECT p.*, 
                   u.name as owner_name,
                   c.name as category_name,
                   d.name as department_name
            FROM post p
            LEFT JOIN user u ON p.owner_id = u.id
            LEFT JOIN category c ON p.category_id = c.id
            LEFT JOIN department d ON p.department_id = d.id
            WHERE p.name LIKE ? OR p.description LIKE ?
            ORDER BY p.created_at DESC
            LIMIT 10
        ''', (f'%{query}%', f'%{query}%'))
        
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
            'department_name': row[10]
        } for row in cr.fetchall()]
        
        return {
            'status': True,
            'data': posts,
            'message': 'Search results retrieved successfully'
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/user/current', methods=['GET'])
def get_current_user():
    # Get token from Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return {'status': False, 'message': 'No token provided'}, 401
    
    token = auth_header.split(' ')[1]
    
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Get user info from session token
        cr.execute('''
            SELECT u.*, s.expired_at
            FROM user u
            JOIN session s ON u.id = s.user_id
            WHERE s.token = ?
        ''', (token,))
        
        user_data = cr.fetchone()
        
        if not user_data:
            return {'status': False, 'message': 'Invalid token'}, 401
            
        # Check if session is expired
        expired_at = datetime.fromisoformat(user_data[-1])
        if datetime.now() > expired_at:
            return {'status': False, 'message': 'Session expired'}, 401
            
        # Check if user is banned
        if user_data[10]:  # banned field
            return {'status': False, 'message': 'User is banned'}, 403
            
        # Return user data
        user = {
            'id': user_data[0],
            'name': user_data[1],
            'bio': user_data[2],
            'email': user_data[3],
            'address': user_data[4],
            'phone': user_data[5],
            'city': user_data[7],
            'department': user_data[8],
            'points': user_data[9],
            'banned': user_data[10],
            'profile_picture': user_data[11] if len(user_data) > 11 else None,
            'admin': user_data[12] if len(user_data) > 12 else False
        }
        
        return {
            'status': True,
            'data': user,
            'message': 'Current user retrieved successfully'
        }
        
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/post/<int:post_id>/attachments', methods=['GET'])
def get_post_attachments(post_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('''
            SELECT * FROM attachment 
            WHERE post_id = ?
            ORDER BY created_at DESC
        ''', (post_id,))
        
        attachments = [{
            'id': row[0],
            'post_id': row[1],
            'file_name': row[2],
            'file_path': row[3],
            'file_type': row[4],
            'file_size': row[5],
            'created_at': row[6]
        } for row in cr.fetchall()]
        
        return {
            'status': True,
            'data': attachments,
            'message': 'Attachments retrieved successfully'
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/post/<int:post_id>/attachment', methods=['POST'])
def upload_attachment(post_id):
    if 'file' not in request.files:
        return {'status': False, 'message': 'No file provided'}, 400
        
    file = request.files['file']
    
    if file.filename == '':
        return {'status': False, 'message': 'No file selected'}, 400
        
    if not allowed_file(file.filename):
        return {'status': False, 'message': 'File type not allowed'}, 400
    
    try:
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save file
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Save attachment info to database
        conn = sqlite3.connect('data.db')
        cr = conn.cursor()
        
        cr.execute('''
            INSERT INTO attachment (post_id, file_name, file_path, file_type, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (post_id, filename, unique_filename, file.content_type, file_size))
        
        conn.commit()
        
        return {
            'status': True,
            'message': 'File uploaded successfully',
            'data': {
                'id': cr.lastrowid,
                'post_id': post_id,
                'file_name': filename,
                'file_path': unique_filename,
                'file_type': file.content_type,
                'file_size': file_size
            }
        }
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/attachment/<int:attachment_id>', methods=['DELETE'])
def delete_attachment(attachment_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        # Get file path before deleting
        cr.execute('SELECT file_path FROM attachment WHERE id = ?', (attachment_id,))
        result = cr.fetchone()
        
        if not result:
            return {'status': False, 'message': 'Attachment not found'}, 404
            
        file_path = os.path.join(UPLOAD_FOLDER, result[0])
        
        # Delete from database
        cr.execute('DELETE FROM attachment WHERE id = ?', (attachment_id,))
        conn.commit()
        
        # Delete file from filesystem
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return {'status': True, 'message': 'Attachment deleted successfully'}
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/attachment/<int:attachment_id>', methods=['GET'])
def download_attachment(attachment_id):
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('SELECT file_name, file_path FROM attachment WHERE id = ?', (attachment_id,))
        result = cr.fetchone()
        
        if not result:
            return {'status': False, 'message': 'Attachment not found'}, 404
            
        file_name, file_path = result
        
        return send_from_directory(
            UPLOAD_FOLDER,
            file_path,
            as_attachment=True,
            download_name=file_name
        )
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

@app.route('/files/<path:filename>')
def serve_file(filename):
    """
    Serve files directly from uploads directory for viewing in browser
    """
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except FileNotFoundError:
        return {'status': False, 'message': 'File not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400

@app.route('/download/<path:filename>')
def download_file(filename):
    """
    Download files directly from uploads directory
    """
    try:
        # Get original filename from database if possible
        conn = sqlite3.connect('data.db')
        cr = conn.cursor()
        
        cr.execute('SELECT file_name FROM attachment WHERE file_path = ?', (filename,))
        result = cr.fetchone()
        
        if result:
            original_name = result[0]
        else:
            # If not found in database, use the filename as is
            original_name = filename
            
        conn.close()
        
        return send_from_directory(
            UPLOAD_FOLDER,
            filename,
            as_attachment=True,
            download_name=original_name
        )
    except FileNotFoundError:
        return {'status': False, 'message': 'File not found'}, 404
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400

@app.route('/attachment/<int:attachment_id>/view', methods=['GET'])
def view_attachment(attachment_id):
    """
    View attachment in browser (not as download)
    """
    conn = sqlite3.connect('data.db')
    cr = conn.cursor()
    
    try:
        cr.execute('SELECT file_name, file_path FROM attachment WHERE id = ?', (attachment_id,))
        result = cr.fetchone()
        
        if not result:
            return {'status': False, 'message': 'Attachment not found'}, 404
            
        file_name, file_path = result
        
        return send_from_directory(
            UPLOAD_FOLDER,
            file_path,
            as_attachment=False  # View in browser instead of download
        )
    except Exception as e:
        return {'status': False, 'message': str(e)}, 400
    finally:
        conn.close()

if __name__ == '__main__':
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()

    # Drop the report table to recreate it with the correct schema
    #cur.execute('DROP TABLE IF EXISTS report')
    
    # Drop all tables (commented out)
    #cur.execute('DROP TABLE IF EXISTS report')
    #cur.execute('DROP TABLE IF EXISTS notification')
    #cur.execute('DROP TABLE IF EXISTS department_pin')
    #cur.execute('DROP TABLE IF EXISTS comment_like')
    #cur.execute('DROP TABLE IF EXISTS post_like')
    #cur.execute('DROP TABLE IF EXISTS session')
    #cur.execute('DROP TABLE IF EXISTS comment')
    #cur.execute('DROP TABLE IF EXISTS post')
    #cur.execute('DROP TABLE IF EXISTS category')
    #cur.execute('DROP TABLE IF EXISTS department')
    #cur.execute('DROP TABLE IF EXISTS faculty')
    # cur.execute('DROP TABLE IF EXISTS user')
    
    # Create tables if they don't exist
    cur.execute('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        bio TEXT,
        email TEXT,
        address TEXT,
        phone TEXT,
        password TEXT,
        city TEXT,
        department TEXT,
        points INTEGER DEFAULT 0,
        banned BOOLEAN DEFAULT FALSE,
        profile_picture TEXT,
        admin BOOLEAN DEFAULT FALSE
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
    cur.execute('''
    CREATE TABLE IF NOT EXISTS notification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        comment_id INTEGER NOT NULL,
        commenter_id INTEGER NOT NULL,
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id),
        FOREIGN KEY (post_id) REFERENCES post (id),
        FOREIGN KEY (comment_id) REFERENCES comment (id),
        FOREIGN KEY (commenter_id) REFERENCES user (id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS report (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        reason TEXT NOT NULL,
        description TEXT,
        post_id INTEGER,
        comment_id INTEGER,
        reporter_id INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES post (id),
        FOREIGN KEY (comment_id) REFERENCES comment (id),
        FOREIGN KEY (reporter_id) REFERENCES user (id)
    )''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS attachment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE
    )''')
    
    # Check if any admin exists
    cur.execute('SELECT COUNT(*) FROM user WHERE admin = TRUE')
    admin_count = cur.fetchone()[0]
    
    # If no admin exists, create one
    if admin_count == 0:
        cur.execute('''
            INSERT INTO user (
                name, email, password, admin
            ) VALUES (?, ?, ?, ?)
        ''', ('Admin', 'admin@admin.com', 'admin123', True))
        print("Created default admin user")
    
    conn.commit()
    conn.close()
    app.run(host='0.0.0.0', port=5001, debug=True)