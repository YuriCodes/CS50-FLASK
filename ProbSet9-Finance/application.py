import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    if request.method == "POST":
        db.execute("""
        UPDATE users
        SET cash = cash +:amount
        WHERE id=:user_id""", amount=request.form.get("cash"),
                user_id=session["user_id"])
        flash("Cash added!")
        return redirect("/")
    else:
        return render_template("addCash.html")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Store the username of the user logged
    rows = db.execute("""
     SELECT symbol, SUM(shares) as totalShares
     FROM portfolio 
     WHERE user_id=:user_id
     GROUP BY symbol 
     HAVING totalShares > 0;
     """, user_id=session["user_id"])
    holdings = []
    grand_total = 0
    for row in rows:
        stock = lookup(row["symbol"])
        holdings.append({
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": row["totalShares"],
            "price": usd(stock["price"]),
            "total": usd(stock["price"] * row["totalShares"])
        })
        grand_total += stock["price"] * row["totalShares"]
    rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = rows[0]["cash"]
    grand_total += cash
    return render_template("index.html", holdings=holdings, cash=usd(cash), grand_total=usd(grand_total))
     
     
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        price = lookup(symbol)
        shares = request.form.get("shares")
        cash = db.execute("SELECT cash FROM users WHERE id = ? ", session["user_id"])[0]["cash"]
        
        if not symbol:
            return apology("provide a valid symbol")
        elif price is None:
            return apology("provide a valid symbol")
            
        try:    
            shares = int(shares)
            if shares < 1:
                return apology("must select one")
        except ValueError:
            return apology("select one")
        
        sharesPrice = shares * price["price"]
        if cash < sharesPrice:
            return apology("You don't have enough cash")
        else:
            db.execute(
                "UPDATE users SET cash = cash - ? WHERE id = ?",
                sharesPrice,
                session["user_id"],
            )
            db.execute("""
            INSERT INTO portfolio (user_id, symbol, shares, price) 
            VALUES (:user_id, :symbol, :shares, :price)
            """,
                    user_id=session["user_id"],
                    symbol=symbol,
                    shares=shares,
                    price=price['price']
                    )
            
            flash("Transaction succesful")
            return redirect("/")
    else:
        return render_template("buy.html")
        
        
@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("""
    SELECT symbol, shares, price, transacted 
    FROM portfolio
    WHERE user_id =:user_id
    """, user_id=session["user_id"])
    for i in range(len(transactions)):
        transactions[i]["price"] = usd(transactions[i]["price"])
    return render_template("history.html", transactions=transactions)
    

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        # Ensure the simbol was submitted
        if quote is None:
            return apology("must provide valid symbol")
        else:
            return render_template(
                "quoted.html",
                name=quote["name"],
                symbol=quote["symbol"],
                price=quote["price"],
            )
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Ensure the username was submitted
        if not username:
            return apology("must provide username", 400)
        # Ensure the username doesn't exists
        elif len(rows) != 0:
            return apology("username already exists", 400)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)

        # Ensure confirmation password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide a confirmation password", 400)

        # Ensure passwords match
        elif not password == confirmation:
            return apology("passwords must match", 400)

        else:
            # Generate the hash of the password
            hash = generate_password_hash(
                password, method="pbkdf2:sha256", salt_length=8
            )
            # Insert the new user
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?) ", username, hash,
            )
            # Redirect user to home page
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        price = lookup(symbol)["price"]
        shares = request.form.get("shares")
        stock = lookup(symbol)
        cash = db.execute("SELECT cash FROM users WHERE id =:user_id ", user_id=session["user_id"])
        try:
            shares = int(shares)
            if shares < 1:
                return apology("Select one or more shares")
        except ValueError:
            return apology("Missing symbol")
                
        rows = db.execute("""
        SELECT symbol, SUM(shares) as shares FROM portfolio 
        WHERE user_id =:user_id 
        GROUP BY symbol 
        HAVING shares > 0;
        """, user_id=session["user_id"])
        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["shares"]:
                    return apology("You don't have this number of shares")
            
        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]['cash']
            
        updated_cash = cash + shares * stock['price']
        db.execute("UPDATE users SET cash=:updated_cash WHERE id=:id",
                updated_cash=updated_cash,
                id=session["user_id"])
            
        db.execute("""
        INSERT INTO portfolio (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)""",
                user_id=session["user_id"],
                symbol=symbol,
                shares=-1 * shares,
                price=stock["price"]
                )

        flash("Sold!")
        return redirect("/")
    else:
        rows = db.execute("""
            SELECT symbol
            FROM portfolio WHERE user_id = :user_id
            GROUP BY symbol
            HAVING SUM(shares) > 0;
        """, user_id=session["user_id"])
        return render_template("sell.html", symbols=[row["symbol"] for row in rows])
        

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
