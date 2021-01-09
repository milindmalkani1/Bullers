import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session.get("user_id")

    # variable to hold the sum of all the shares which users had, so that we can add this further into grand total
    sum_of_shares = 0

    # Showing updated portfolio everytime when user land's on home page
    updated_portfolio = db.execute("SELECT * from portfolio \
                                    WHERE id=:user_id", user_id=user_id)

    # selecting the cash which users had left after all transactions into users table
    left_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session.get("user_id"))

    # loop to convert each share price and total shares price into required format using uds function
    # and also calculating total value of all the shares
    for i in range(len(updated_portfolio)):
        sum_of_shares = sum_of_shares + int(updated_portfolio[i]['total_price'])
        updated_portfolio[i]['price'] = usd(updated_portfolio[i]['price'])
        updated_portfolio[i]['total_price'] = usd(updated_portfolio[i]['total_price'])

    # adding the above calculated value of the shares to the left_cash the user have
    grand_total = left_cash[0]['cash'] + sum_of_shares

    return render_template("index.html", grand_total=usd(grand_total), stocks=updated_portfolio, left_cash=usd(left_cash[0]['cash']))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        find_missing = is_provided("symbol") or is_provided("shares")
        if find_missing:
            return find_missing
        elif not request.form.get("shares").isdigit():
            return apology("invalid number of shares")
        symbol = request.form.get("symbol").upper()
        share = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol")
        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]["cash"]

        updated_cash = cash - (share * stock['price'])
        if updated_cash < 0:
            return apology("can't afford")
        else:
            db.execute("UPDATE users SET cash=:updated_cash WHERE id=:id",
                        updated_cash=updated_cash,
                        id=session["user_id"])

            #if the user's id doesn't associated with the given symbol than insert it
            if not db.execute("SELECT id FROM portfolio WHERE symbol=:stock_name_capital", stock_name_capital=stock['symbol']):
                db.execute("INSERT INTO portfolio(id, shares, symbol, total_price, price) \
                            VALUES(:user_id, :share, :stock_name_capital, :total_shares_price, :cost)",
                            user_id=session["user_id"], share=share, stock_name_capital=stock['symbol'],
                            total_shares_price=share * stock['price'], cost=stock['price'])
            # else update portfolio by increasing no. of shares and total price of the shares
            else:
                db.execute("UPDATE portfolio SET shares = shares + :share, total_price = total_price + :total_shares_price WHERE symbol=:stock_name_capital AND id = :user_id",
                            share=share, total_shares_price=(share * stock['price']), stock_name_capital=stock['symbol'], user_id=session["user_id"])

                #inserting the transactions into the history table
            db.execute("INSERT INTO history (symbols, shares, price, id) VALUES(:sym, :share, :price, :user_id)",
                           sym=symbol, share=share, price=usd(stock["price"]), user_id=session["user_id"])
            return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    histories = db.execute("SELECT * from history WHERE id=:user_id", user_id=session["user_id"])

    return render_template("history.html", histories=histories)

def is_provided(field):
    if not request.form.get(field):
        return apology(f"must provide {field}", 403)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        result = is_provided("username") or is_provided("password")
        if result is not None:
            return result

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
        result = is_provided("symbol")

        if result is not None:
            return result
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol", 400)

        return render_template("quoted.html", stockName={
            'name': stock['name'],
            'symbol': stock['symbol'],
            'price': usd(stock['price'])
        })

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        result = is_provided("username") or is_provided("password") or is_provided("confirmation")
        if result != None:
            return result

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("password doesn't match")

        try:
            session_key = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    username = request.form.get("username"),
                    hash = generate_password_hash(request.form.get("password")))
        except:
            return apology("username already exists", 403)


        if session_key is None:
            return apology("registration error", 403)
        session["user_id"] = session_key

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session.get("user_id")

    #when the user hits the submit button accessing the post request
    if request.method == "POST":

        #requesting the symbol from the form which user entered
        sym = request.form.get("symbol").upper()

        # Getting the symbol name, price and symbol in the form of dictionary quote using function lookup
        quote = lookup(sym)

        # Selecting shares from the portfolio table to further deduct them after selling
        shares_of_user = db.execute("SELECT shares FROM portfolio WHERE id=:user_id AND symbol=:sym", user_id=user_id, sym=sym)

        #getting the number of shares which the user entered
        sha = request.form.get("shares")

        #checking if the symbol is entered or not
        if not sym:

            return apology("please enter symbol", 400)
        #checkin if the no. of shares are entered and the entered number is negative or not
        elif not sha or int(sha) < 1:

            return apology("please enter valid number of shares", 400)

        #checking if the entered no. of shares are more than the number of shares which user had so that
        #we can display apology
        elif int(sha) > shares_of_user[0]["shares"]:

            return apology("too many shares", 400)

        #if all above checks passes
        else:
            #getting the current cost of the shares and mult it with the number of shares to get the total price
            current_cost = float(quote['price']) * float(sha)

            #after selling updating the cash of the user
            db.execute("UPDATE users SET cash = cash + :current_cost WHERE id=:user_id", current_cost=current_cost,  user_id=user_id)

            #decreasing the number of shares which the user will currently own after selling shares to keep track whether the user
            #hit zero no of shares
            shares_of_user = shares_of_user[0]['shares'] - int(sha)
            #if after the process of deduction of shares user left zero shares than delete his record from the portfolio page
            if shares_of_user == 0:

                db.execute("DELETE FROM portfolio WHERE id=:user_id AND symbol=:sym", user_id=user_id, sym=sym)

            #else decrease the number of shares
            else:

                db.execute("UPDATE portfolio SET shares = shares - :sha WHERE id=:user_id AND symbol=:sym", sha=sha, user_id=user_id,
                           sym=sym)
            #inserting the transaction details into the history table
            db.execute("INSERT INTO history (symbols, shares, price, id) VALUES(:sym, :share, :price, :user_id)",
                       sym=sym, share=sha, price=usd(quote["price"]), user_id=user_id)

            return redirect("/")

    # if the user clicked the link of the sell from the page(or the get request)
    else:

        user_id = session.get("user_id")

        share_symbols = db.execute("SELECT symbol FROM portfolio WHERE id=:user_id", user_id=user_id)

        return render_template("sell.html", share_symbol=share_symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
