
from flask import Flask, render_template, request, redirect, url_for, session, jsonify,flash
from flask_mysqldb import MySQL
from datetime import datetime
app = Flask(__name__)

# Secret key for session management
app.secret_key = 'your_secret_key'

# MySQL configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'ecommerce'

mysql = MySQL(app)

# Home Route
@app.route('/')
def index():
    cursor = mysql.connection.cursor()

    # Query to fetch top-selling products based on sales quantity
    cursor.execute('''
        SELECT Products.*, SUM(Orders.quantity) AS total_sales
        FROM Products
        JOIN Orders ON Products.ID = Orders.product_id
        GROUP BY Products.ID
        ORDER BY total_sales DESC
        LIMIT 6
    ''')

    top_trending_products = cursor.fetchall()
    cursor.close()

    return render_template('index.html', products=top_trending_products)


@app.route('/customer_home', methods=['GET'])
def customer_home():
    if 'loggedin' in session:
        customer_id = session['id']
        cursor = mysql.connection.cursor()

        # Fetch customer name from the database
        cursor.execute('SELECT name FROM Customers WHERE ID = %s', (customer_id,))
        customer_name = cursor.fetchone()[0]



        # Fetch top trending products
        cursor.execute('''
                SELECT Products.*, SUM(Orders.quantity) AS total_sales
                FROM Products
                JOIN Orders ON Products.ID = Orders.product_id
                GROUP BY Products.ID
                ORDER BY total_sales DESC
                LIMIT 6
            ''')
        products = cursor.fetchall()
        # Get the number of items in the cart
        cursor.execute('''
                SELECT SUM(number_of_product)
                FROM Cart
                WHERE customer_id = %s
            ''', (customer_id,))
        cart_item_count = cursor.fetchone()[0] or 0
        cursor.close()

        return render_template('customer_home.html',
                               customer_name=customer_name,
                               products=products,
                               cart_item_count=cart_item_count)
    return redirect(url_for('login'))  # Redirect to login if not logged in

@app.route('/add_to_cart/<int:product_id>', methods=['GET', 'POST'])
def add_to_cart(product_id):
    if 'loggedin' in session:
        # If logged in, process the cart addition in the database
        customer_id = session['id']
        cursor = mysql.connection.cursor()

        cursor.execute('''
            SELECT number_of_product FROM Cart WHERE customer_id = %s AND product_id = %s
        ''', (customer_id, product_id))
        existing_item = cursor.fetchone()

        if existing_item:
            new_quantity = existing_item[0] + 1
            cursor.execute('''
                UPDATE Cart SET number_of_product = %s
                WHERE customer_id = %s AND product_id = %s
            ''', (new_quantity, customer_id, product_id))
        else:
            cursor.execute('''
                INSERT INTO Cart (customer_id, product_id, number_of_product)
                VALUES (%s, %s, %s)
            ''', (customer_id, product_id, 1))  # Default quantity is 1

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('view_cart'))

    else:
        # If not logged in, store in session
        if 'cart' not in session:
            session['cart'] = []

        session['cart'].append(product_id)
        session.modified = True
        return redirect(url_for('add_to_cart_prompt'))


@app.route('/add_to_cart_prompt', methods=['GET', 'POST'])
def add_to_cart_prompt():
    if request.method == 'POST':
        action = request.form['action']

        if action == 'login':
            return redirect(url_for('login'))  # Redirect to login page
        elif action == 'register':
            return redirect(url_for('register'))  # Redirect to register page
        elif action == 'continue_as_guest':
            return redirect(url_for('guest_checkout'))  # Redirect to guest checkout page

    return render_template('add_to_cart_prompt.html')

@app.route('/guest_checkout', methods=['GET', 'POST'])
def guest_checkout():
    if request.method == 'POST':
        address = request.form['address']
        phone = request.form['phone']

        # Store guest information in the Customers table
        cursor = mysql.connection.cursor()

        # Insert new guest into the Customers table with 'Guest' type
        cursor.execute('''
            INSERT INTO Customers ( name,email,phone, address, type)
            VALUES (%s,%s, %s, %s, %s)
        ''', ('Guest', phone,phone, address, 'Guest'))  # 'Guest' values for name, email, and password
        mysql.connection.commit()

        # Get the customer ID of the newly created guest user
        cursor.execute('SELECT LAST_INSERT_ID()')
        customer_id = cursor.fetchone()[0]

        # Store the customer_id in session for future use (if needed)
        session['id'] = customer_id
        session['loggedin'] = True
        session['name']= phone
        # Now link the cart items to the newly created guest customer
        if 'cart' in session:
            for product_id in session['cart']:
                cursor.execute('''
                    INSERT INTO Cart (customer_id, product_id, number_of_product)
                    VALUES (%s, %s, %s)
                ''', (customer_id, product_id, 1))  # Default quantity of 1 for each product
            mysql.connection.commit()

        # Clear the guest cart session after checkout
        session.pop('cart', None)

        cursor.close()

        # Redirect to view_cart page or confirmation page
        return redirect(url_for('view_cart'))  # or redirect to another page like a confirmation page

    return render_template('guest_checkout.html')  # Show guest checkout form


@app.route('/remove_from_cart/<int:product_id>', methods=['GET'])
def remove_from_cart(product_id):
    if 'loggedin' in session:
        customer_id = session['id']
        cursor = mysql.connection.cursor()

        # Remove the product from the customer's cart by matching customer_id and product_id
        cursor.execute('DELETE FROM Cart WHERE customer_id = %s AND product_id = %s', (customer_id, product_id))
        mysql.connection.commit()

        cursor.close()
        return redirect(url_for('view_cart'))  # Redirect back to the cart

    return redirect(url_for('login'))  # Redirect to login if not logged in

@app.route('/view_cart', methods=['GET'])
def view_cart():
    if 'loggedin' in session:
        customer_id = session['id']
        cursor = mysql.connection.cursor()

        # Fetch cart items for the logged-in customer, including the product details
        cursor.execute('''
            SELECT p.ID, p.name, p.description, p.price, c.number_of_product
            FROM Cart c
            JOIN Products p ON c.product_id = p.ID
            WHERE c.customer_id = %s
        ''', (customer_id,))
        cart_items = cursor.fetchall()

        # Calculate total price of the cart based on quantity and price
        cursor.execute('''
            SELECT SUM(p.price * c.number_of_product)
            FROM Cart c
            JOIN Products p ON c.product_id = p.ID
            WHERE c.customer_id = %s
        ''', (customer_id,))
        total_price = cursor.fetchone()[0] or 0  # Handle case if no items exist in the cart

        # Calculate total quantity of items in the cart
        cursor.execute('''
            SELECT SUM(number_of_product) FROM Cart WHERE customer_id = %s
        ''', (customer_id,))
        cart_qty = cursor.fetchone()[0] or 0

        cursor.close()

        return render_template('view_cart.html', cart_items=cart_items, total_price=total_price, cart_qty=cart_qty)

    return redirect(url_for('login'))  # Redirect to login if not logged in


@app.route('/checkout', methods=['GET'])
def checkout():
    if 'loggedin' in session:
        customer_id = session['id']
        cursor = mysql.connection.cursor()

        # Fetch cart items for the logged-in customer
        cursor.execute('''
            SELECT c.product_id, p.price, c.number_of_product, p.quantity
            FROM Cart c
            JOIN Products p ON c.product_id = p.ID
            WHERE c.customer_id = %s
        ''', (customer_id,))
        cart_items = cursor.fetchall()

        if cart_items:
            # Place an order for each item in the cart
            for item in cart_items:
                product_id = item[0]
                price = item[1]
                quantity = item[2]
                product_stock = item[3]

                # Ensure there is enough stock
                if product_stock >= quantity:
                    # Insert into the Orders table
                    cursor.execute('''
                        INSERT INTO Orders (customer_id, product_id, quantity, order_date)
                        VALUES (%s, %s, %s, %s)
                    ''', (customer_id, product_id, quantity, datetime.now().date()))

                    # Update the product quantity in the Products table
                    new_quantity = product_stock - quantity
                    cursor.execute('''
                        UPDATE Products
                        SET quantity = %s
                        WHERE ID = %s
                    ''', (new_quantity, product_id))

                    # Remove the item from the cart
                    cursor.execute('''
                        DELETE FROM Cart
                        WHERE customer_id = %s AND product_id = %s
                    ''', (customer_id, product_id))

                else:
                    # If stock is not enough, you might want to notify the user
                    print(f"Not enough stock for product {product_id}")

            mysql.connection.commit()

            cursor.close()
            return redirect(url_for('order_confirmation'))  # Redirect to a confirmation page or similar

        cursor.close()
        return redirect(url_for('view_cart'))  # Redirect back to the cart if cart is empty

    return redirect(url_for('login'))  # Redirect to login if not logged in

@app.route('/order_confirmation', methods=['GET'])
def order_confirmation():
    return render_template('order_confirmation.html')

# Register Route

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        print(request.form)  # Debug: Log the form data

        # Ensure all required fields are provided
        if all(key in request.form for key in ['username', 'email', 'password', 'user_type']):
            name = request.form['username']  # 'username' in form corresponds to 'name' in DB
            email = request.form['email']
            password = request.form['password']
            user_type = request.form['user_type']  # This will be 'customer' or 'seller'
            phone = request.form.get('phone')  # Optional field
            address = request.form.get('address')  # Optional field

            cursor = mysql.connection.cursor()

            try:
                # Insert into the appropriate table based on user_type
                if user_type == 'customer':
                    cursor.execute(
                        '''
                        INSERT INTO Customers (name, email, password, phone, address, type)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ''',
                        (name, email, password, phone, address, 'Individual')
                    )
                elif user_type == 'seller':
                    cursor.execute(
                        '''
                        INSERT INTO Sellers (name, email, password, phone, address)
                        VALUES (%s, %s, %s, %s, %s)
                        ''',
                        (name, email, password, phone, address)
                    )

                mysql.connection.commit()
                flash('Registration successful!', 'success')
                return redirect(url_for('index'))

            except Exception as e:
                mysql.connection.rollback()
                print(f"Database Error: {e}")  # Debug database errors
                flash('An error occurred during registration. Please try again.', 'danger')

            finally:
                cursor.close()

        else:
            flash('All required fields must be filled!', 'danger')

    # Render the registration form for GET or in case of an error
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST' and 'email' in request.form and 'password' in request.form:
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM customers WHERE email = %s', (email,))
        account = cursor.fetchone()
        cursor.close()

        if not account:
            error = 'Account with this email does not exist!'
        elif account[3] != password:  # Compare password field (account[3])
            error = 'Incorrect password!'
        else:
            session['loggedin'] = True  # Set loggedin session to True
            session['id'] = account[0]  # account[0] is id
            session['name'] = account[1]  # account[1] is name
            if 'cart' in session:
                # Assuming session["cart"] exists and is a list or string representation
                print(session["cart"])

                # Redirecting to add_to_cart with cart as a query parameter
                return redirect(url_for('add_to_cart', product_id=session["cart"][0]))

            return redirect(url_for('customer_dashboard'))  # Redirect to dashboard

    return render_template('login.html', error=error)

@app.route('/customer/dashboard')
def customer_dashboard():
    if 'loggedin' in session:  # Check if logged in
        customer_id = session['id']  # Use session['id'] instead of session['customer_id']
        customer_name = session['name']  # Use session['name'] instead of session['customer_name']

        cursor = mysql.connection.cursor()

        # Fetch total orders placed by the customer
        cursor.execute(''' 
            SELECT COUNT(*) AS total_orders, 
                   SUM(Orders.quantity * Products.price) AS total_spent
            FROM Orders
            JOIN Products ON Orders.product_id = Products.ID
            WHERE Orders.customer_id = %s
        ''', (customer_id,))
        result = cursor.fetchone()
        total_orders = result[0]
        total_spent = result[1] if result[1] else 0

        # Fetch recent orders for the customer, including status
        cursor.execute(''' 
            SELECT Orders.order_no, Products.name AS product_name, Orders.quantity, Orders.order_date, Products.price, Orders.status
            FROM Orders
            JOIN Products ON Orders.product_id = Products.ID
            WHERE Orders.customer_id = %s
            ORDER BY Orders.order_date DESC
            LIMIT 5
        ''', (customer_id,))
        recent_orders = cursor.fetchall()

        # Fetch customer information
        cursor.execute('SELECT * FROM Customers WHERE ID = %s', (customer_id,))
        customer_info = cursor.fetchone()

        cursor.close()

        return render_template(
            'customer_dashboard.html',
            name=customer_name,  # Pass session['name'] as customer_name
            total_orders=total_orders,
            total_spent=total_spent,
            recent_orders=recent_orders,
            customer_info=customer_info
        )

    return redirect(url_for('login'))  # If not logged in, redirect to login



@app.route('/customer/order_tracking')
def order_tracking():
    if 'loggedin' in session:
        customer_id = session['id']

        cursor = mysql.connection.cursor()

        # Fetch orders of the customer, including seller's name, quantity, and total spent
        cursor.execute('''
            SELECT Orders.order_no, Orders.order_date, Orders.status, 
                   Sellers.name AS seller_name, Orders.quantity, 
                   SUM(Orders.quantity * Products.price) AS total_spent
            FROM Orders
            JOIN Products ON Orders.product_id = Products.ID
            JOIN Sellers ON Products.seller_id = Sellers.SellerID  -- Use SellerID here
            WHERE Orders.customer_id = %s
            GROUP BY Orders.order_no, Sellers.name
        ''', (customer_id,))
        orders = cursor.fetchall()

        cursor.close()

        return render_template('order_tracking.html', orders=orders)

    return redirect(url_for('login'))  # If not logged in, redirect to login

@app.route('/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    if order_id is None:
        # Handle the case where order_id is not passed correctly
        return "Order ID is missing", 400
    cursor = mysql.connection.cursor()

    # Get the order details to retrieve the product and quantity
    cursor.execute('''
        SELECT product_id, quantity, status
        FROM Orders
        WHERE order_no = %s
    ''', (order_id,))
    order = cursor.fetchone()

    if order:
        product_id = order[0]
        quantity = order[1]
        status = order[2]

        # If the status was 'Shipped', increase the product quantity by 1
        if status == 'Shipped':
            cursor.execute('''
                UPDATE Products
                SET quantity = quantity + 1
                WHERE ID = %s
            ''', (product_id,))
            mysql.connection.commit()

        # Delete the order
        cursor.execute('''
            DELETE FROM Orders
            WHERE order_no = %s
        ''', (order_id,))
        mysql.connection.commit()

    cursor.close()
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/update_account', methods=['GET', 'POST'])
def update_account():
    if 'loggedin' in session:
        customer_id = session['id']

        cursor = mysql.connection.cursor()

        # Fetch current customer info
        cursor.execute('SELECT * FROM Customers WHERE ID = %s', (customer_id,))
        customer_info = cursor.fetchone()

        if request.method == 'POST':
            new_email = request.form['email']
            new_name = request.form['name']
            new_phone = request.form['phone']
            new_address = request.form['address']
            new_password = request.form['password']

            # Check if password was provided
            if new_password:
                # Update customer information with password
                cursor.execute('''
                    UPDATE Customers
                    SET email = %s, name = %s, phone = %s, address = %s, password = %s
                    WHERE ID = %s
                ''', (new_email, new_name, new_phone, new_address, new_password, customer_id))
            else:
                # Update customer information without changing the password
                cursor.execute('''
                    UPDATE Customers
                    SET email = %s, name = %s, phone = %s, address = %s
                    WHERE ID = %s
                ''', (new_email, new_name, new_phone, new_address, customer_id))

            mysql.connection.commit()
            cursor.close()

            # After update, redirect to the dashboard
            return redirect(url_for('customer_dashboard'))

        cursor.close()

        return render_template('update_account.html', customer_info=customer_info)

    return redirect(url_for('login'))  # If not logged in, redirect to login



'''# Dashboard Route
@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        return render_template('dashboard.html')
        #return f'Welcome {session["name"]}!'
    #return redirect(url_for('login'))'''

# Seller Registration
@app.route('/seller/register', methods=['GET', 'POST'])
def seller_register():
    if request.method == 'POST' and 'name' in request.form and 'email' in request.form and 'password' in request.form:
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO sellers (name, email, password) VALUES (%s, %s, %s)', (name, email, password))
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('seller_login'))
    return render_template('seller_register.html')



@app.route('/seller/account_information', methods=['GET'])
def account_information():
    if 'seller_loggedin' in session:  # Ensure user is logged in and is a seller
        seller_id = session['seller_id']  # Fetch seller's ID from the session

        # Create a cursor object to interact with the database
        cursor = mysql.connection.cursor()

        # Query to fetch the seller's account details
        cursor.execute('''
            SELECT name, email, phone, address FROM Sellers WHERE SellerID = %s
        ''', (seller_id,))

        # Fetch the seller's data

        seller_info = cursor.fetchone()

        cursor.close()

        if seller_info:
            # Render the template and pass the seller information
            return render_template('account_information.html', seller=seller_info)
        else:
            # Redirect to dashboard or show an error if no seller found
            return redirect(url_for('seller_dashboard'))
    else:
        # If not logged in, redirect to login page
        return redirect(url_for('login'))

@app.route('/update_seller_account', methods=['GET', 'POST'])
def update_seller_account():
    if 'seller_loggedin' in session:
        seller_id = session['seller_id']  # Assuming seller's ID is stored in the session

        cursor = mysql.connection.cursor()

        # Fetch current seller info
        cursor.execute('SELECT * FROM Sellers WHERE sellerID = %s', (seller_id,))
        seller_info = cursor.fetchone()
        print(seller_info)

        if request.method == 'POST':
            new_email = request.form['email']
            new_name = request.form['name']
            new_phone = request.form['phone']

            new_address = request.form['address']
            new_password = request.form['password']

            # Check if password was provided
            if new_password:
                # Update seller information with password
                cursor.execute('''
                    UPDATE Sellers
                    SET email = %s, name = %s, phone = %s, address = %s, password = %s
                    WHERE sellerID = %s
                ''', (new_email, new_name, new_phone, new_address, new_password, seller_id))
            else:
                # Update seller information without changing the password
                cursor.execute('''
                    UPDATE Sellers
                    SET email = %s, name = %s, phone = %s, address = %s
                    WHERE sellerID = %s
                ''', (new_email, new_name, new_phone, new_address, seller_id))

            mysql.connection.commit()
            cursor.close()

            # After update, redirect to the seller dashboard or profile page
            return redirect(url_for('account_information'))

        cursor.close()

        return render_template('update_seller_information.html', seller_info=seller_info)

    return redirect(url_for('seller_login'))  # If not logged in, redirect to login
# Seller Login

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    if request.method == 'POST' and 'email' in request.form and 'password' in request.form:
        email = request.form['email']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM sellers WHERE email = %s', (email,))
        account = cursor.fetchone()
        cursor.close()

        if not account:
            return 'Account with this email does not exist!'

        # Compare plain text passwords directly
        if account[3] != password:  # account[3] refers to the password field
            return 'Incorrect password!'
        else:
            session['seller_loggedin'] = True
            session['seller_id'] = account[0]  # account[0] refers to the id field
            session['seller_name'] = account[1]  # account[1] refers to the name field
            return redirect(url_for('seller_dashboard'))
    return render_template('seller_login.html')

@app.route('/search_results', methods=['GET'])
def search_results():
    search_query = request.args.get('search_query', '')

    cursor = mysql.connection.cursor()

    # Execute the query to find products that match the search query
    cursor.execute('''
        SELECT * FROM Products
        WHERE name LIKE %s OR description LIKE %s
    ''', ('%' + search_query + '%', '%' + search_query + '%'))

    products = cursor.fetchall()
    print(products)
    cursor.close()

    return render_template('search_results.html', products=products, search_query=search_query)



@app.route('/view_product/<int:product_id>', methods=['GET'])
def view_product(product_id):
    cursor = mysql.connection.cursor()

    # Modified query to fetch product and seller details in one query
    cursor.execute("""
        SELECT Products.*, Sellers.name AS seller_name, Sellers.email AS seller_email, 
               Sellers.phone AS seller_phone, Sellers.address AS seller_address
        FROM Products
        JOIN Sellers ON Products.Seller_id = Sellers.SellerID
        WHERE Products.ID = %s
    """, (product_id,))

    product = cursor.fetchone()
    cursor.close()
    # Check if the product exists
    if not product:
        return "Product not found", 404
    if 'loggedin' in session:
        return render_template('logged_view_product.html', product=product, customer_name= session['name'])
    # Pass both product and seller data to the template
    else:
        return render_template('view_product.html', product=product)


@app.route('/seller/dashboard')
def seller_dashboard():
    if 'seller_loggedin' in session:
        seller_id = session['seller_id']

        cursor = mysql.connection.cursor()

        # Fetch total orders, total price, and weekly sales for the seller
        cursor.execute('''
            SELECT 
                COUNT(*) AS total_orders,
                SUM(Products.price * Orders.quantity) AS total_price,
                SUM(
                    CASE 
                        WHEN Orders.order_date >= CURDATE() - INTERVAL 7 DAY THEN Products.price * Orders.quantity
                        ELSE 0
                    END
                ) AS weekly_sales,
                COUNT(
                    CASE 
                        WHEN Orders.order_date >= CURDATE() - INTERVAL 7 DAY THEN 1
                        ELSE NULL
                    END
                ) AS weekly_sales_count
            FROM Orders
            JOIN Products ON Orders.product_id = Products.ID
            WHERE Products.Seller_id = %s
        ''', (seller_id,))

        result = cursor.fetchone()
        total_orders = result[0]
        total_price = result[1] if result[1] else 0
        weekly_sales = result[2] if result[2] else 0
        weekly_sales_count = result[3] if result[3] else 0

        # Fetch low stock products (example: quantity less than 10)
        cursor.execute('''
            SELECT * FROM Products
            WHERE Seller_id = %s AND quantity < 10
        ''', (seller_id,))
        low_stock_products = cursor.fetchall()

        # Fetch received orders for the seller
        # Fetch received orders for the seller
        cursor.execute('''
            SELECT Orders.order_no, Customers.name AS customer_name, Products.name AS product_name,
                   Orders.quantity, Orders.order_date, Products.price as price
            FROM Orders
            JOIN Customers ON Orders.customer_id = Customers.ID
            JOIN Products ON Orders.product_id = Products.ID
            WHERE Products.Seller_id = %s
        ''', (seller_id,))
        received_orders = cursor.fetchall()

        cursor.close()

        # Fetch the seller's products
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM Products WHERE Seller_id = %s', (seller_id,))
        products = cursor.fetchall()
        cursor.close()
        print(received_orders)

        return render_template(
            'seller_dashboard.html',
            name=session['seller_name'],
            total_orders=total_orders,
            total_price=total_price,
            weekly_sales=weekly_sales,
            weekly_sales_count=weekly_sales_count,
            products=products,
            low_stock_products=low_stock_products,
            received_orders=received_orders
        )

    return redirect(url_for('seller_login'))
@app.route('/category/<category_name>')
def category(category_name):
    # Create a cursor to execute SQL queries
    cursor = mysql.connection.cursor()

    # SQL query to fetch products from the specified category
    query = """
    SELECT ID, name, description, price, quantity, manufacture_date, category, author, type, expiration_date
    FROM Products
    WHERE category = %s
    """
    cursor.execute(query, (category_name,))

    # Fetch all results
    products = cursor.fetchall()
    print(products)
    # Close the cursor
    cursor.close()

    if not 'loggedin' in session:
        return render_template('category.html', category_name=category_name, products=products)
    else:

        return render_template('logged_category.html', category_name=category_name, products=products,  customer_name= session['name'])




@app.route('/view_order/<int:order_id>')
def view_order(order_id):
    cursor = mysql.connection.cursor()

    # Fetch order details including customer's address and total price
    cursor.execute('''
        SELECT Orders.order_no, 
               Customers.name AS customer_name, 
               Customers.address AS customer_address, 
               Products.name AS product_name, 
               Orders.quantity, 
               Orders.order_date,
               Products.price, 
               (Orders.quantity * Products.price) AS total_price,
               orders.status as status
        FROM Orders
        JOIN Customers ON Orders.customer_id = Customers.ID
        JOIN Products ON Orders.product_id = Products.ID
        WHERE Orders.order_no = %s
    ''', (order_id,))
    order = cursor.fetchone()
    print(order)
    cursor.close()

    if order:
        return render_template(
            'view_order.html',
            order=order
        )
    else:
        return "Order not found", 404



@app.route('/mark_shipped/<int:order_id>', methods=['POST'])
def mark_shipped(order_id):
    cursor = mysql.connection.cursor()

    # Get the order details to retrieve the product and quantity
    cursor.execute('''
        SELECT product_id, quantity
        FROM Orders
        WHERE order_no = %s
    ''', (order_id,))
    order = cursor.fetchone()

    if order:
        product_id = order[0]
        quantity = order[1]

        # Check if the product has enough stock to fulfill the order
        cursor.execute('''
            SELECT quantity FROM Products WHERE ID = %s
        ''', (product_id,))
        product = cursor.fetchone()

        if product and product[0] >= quantity:
            # Update the status to 'Shipped' and set the shipment date
            cursor.execute('''
                UPDATE Orders
                SET status = 'Shipped', shipment_date = NOW()
                WHERE order_no = %s
            ''', (order_id,))
            mysql.connection.commit()

            # Decrease the product quantity by order quantity
            cursor.execute('''
                UPDATE Products
                SET quantity = quantity - %s
                WHERE ID = %s
            ''', (quantity, product_id))
            mysql.connection.commit()
        else:
            cursor.close()
            return "Error: Not enough product stock to fulfill the order.", 400

    cursor.close()
    return redirect(url_for('view_order', order_id=order_id))


@app.route('/cancel_order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    cursor = mysql.connection.cursor()

    # Get the order details to retrieve the product and quantity
    cursor.execute('''
        SELECT product_id, quantity, status
        FROM Orders
        WHERE order_no = %s
    ''', (order_id,))
    order = cursor.fetchone()

    if order:
        product_id = order[0]
        quantity = order[1]
        status = order[2]

        # Update the status to 'Canceled'
        cursor.execute('''
            UPDATE Orders
            SET status = 'Canceled'
            WHERE order_no = %s
        ''', (order_id,))
        mysql.connection.commit()

        # If the status was 'Shipped' or 'Canceled', increase the product quantity
        if status == 'Shipped' or status == 'Canceled':
            cursor.execute('''
                UPDATE Products
                SET quantity = quantity + %s
                WHERE ID = %s
            ''', (quantity, product_id))
            mysql.connection.commit()

    cursor.close()
    return redirect(url_for('view_order', order_id=order_id))




@app.route('/get_sales_summary', methods=['GET'])
def get_sales_summary():
    if 'seller_id' not in session:
        return jsonify({'error': 'Unauthorized access'}), 403

    seller_id = session['seller_id']
    cursor = mysql.connection.cursor()

    # Aggregate sales statistics query
    cursor.execute('''
        SELECT 
            SUM(o.quantity) AS total_quantity_all_time,
            SUM(o.quantity * p.price) AS total_sales_all_time,
            SUM(CASE WHEN o.order_date >= CURDATE() - INTERVAL 21 DAY THEN o.quantity ELSE 0 END) AS total_quantity_21_days,
            SUM(CASE WHEN o.order_date >= CURDATE() - INTERVAL 21 DAY THEN o.quantity * p.price ELSE 0 END) AS total_sales_21_days,
            SUM(CASE WHEN o.order_date >= CURDATE() - INTERVAL 14 DAY THEN o.quantity ELSE 0 END) AS total_quantity_14_days,
            SUM(CASE WHEN o.order_date >= CURDATE() - INTERVAL 14 DAY THEN o.quantity * p.price ELSE 0 END) AS total_sales_14_days,
            SUM(CASE WHEN o.order_date >= CURDATE() - INTERVAL 7 DAY THEN o.quantity ELSE 0 END) AS total_quantity_7_days,
            SUM(CASE WHEN o.order_date >= CURDATE() - INTERVAL 7 DAY THEN o.quantity * p.price ELSE 0 END) AS total_sales_7_days
        FROM Products p
        LEFT JOIN Orders o ON p.ID = o.product_id
        WHERE p.Seller_id = %s
    ''', (seller_id,))

    result = cursor.fetchone()
    cursor.close()

    # Format the response
    sales_summary = {
        'total_quantity_all_time': result[0] if result[0] else 0,
        'total_sales_all_time': result[1] if result[1] else 0.0,
        'total_quantity_21_days': result[2] if result[2] else 0,
        'total_sales_21_days': result[3] if result[3] else 0.0,
        'total_quantity_14_days': result[4]-result[6] if result[4] else 0,
        'total_sales_14_days': result[5]-result[7] if result[5] else 0.0,
        'total_quantity_7_days': result[6]-result[0] if result[6] else 0,
        'total_sales_7_days': result[7]- result[1] if result[7] else 0.0
    }

    return jsonify(sales_summary)

# Seller Dashboard
'''@app.route('/seller/dashboard')
def seller_dashboard():
    if 'seller_loggedin' in session:
        seller_id = session['seller_id']
        # Fetch the seller's products from the database
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM products WHERE seller_id = %s', (seller_id,))
        products = cursor.fetchall()
        cursor.close()
        print(products)
        return render_template('seller_dashboardold.html', name=session['seller_name'], products=products)
    return redirect(url_for('seller_login'))'''


@app.route('/seller/update_product/<int:product_id>', methods=['GET', 'POST'])
def update_product(product_id):
    if 'seller_loggedin' in session:
        cursor = mysql.connection.cursor()

        # Fetch the product details
        cursor.execute('SELECT * FROM products WHERE id = %s AND seller_id = %s', (product_id, session['seller_id']))
        product = cursor.fetchone()

        if not product:
            return 'Product not found or unauthorized', 404

        if request.method == 'POST':
            name = request.form['name']
            description = request.form['description']
            price = request.form['price']
            quantity = request.form['quantity']

            # Update the product details
            cursor.execute('''
                UPDATE products 
                SET name = %s, description = %s, price = %s, quantity = %s 
                WHERE id = %s
            ''', (name, description, price, quantity, product_id))
            mysql.connection.commit()
            cursor.close()
            return redirect(url_for('seller_dashboard'))

        cursor.close()
        return render_template('update_product.html', product=product)
    return redirect(url_for('seller_login'))


@app.route('/seller/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'seller_loggedin' in session:
        cursor = mysql.connection.cursor()

        # Delete the product owned by the seller
        cursor.execute('DELETE FROM products WHERE id = %s AND seller_id = %s', (product_id, session['seller_id']))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('seller_dashboard'))
    return redirect(url_for('seller_login'))


# Add Product (Seller Feature)
@app.route('/seller/add_product', methods=['GET', 'POST'])
def add_product():
    if 'seller_loggedin' in session:
        if request.method == 'POST' and 'name' in request.form and 'price' in request.form and 'quantity' in request.form:
            name = request.form['name']
            price = request.form['price']
            quantity = request.form['quantity']
            description = request.form['description']
            seller_id = session['seller_id']

            cursor = mysql.connection.cursor()
            cursor.execute('INSERT INTO products (name, price, quantity, seller_id, description) VALUES (%s, %s, %s, %s, %s)', (name, price, quantity, seller_id, description))
            mysql.connection.commit()
            cursor.close()
            return redirect(url_for('seller_dashboard'))
        return render_template('add_product.html')
    return redirect(url_for('seller_login'))


# Logout Route (for both customers and sellers)
@app.route('/logout',methods =['GET','POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))




if __name__ == '__main__':
    app.run(debug=True)
