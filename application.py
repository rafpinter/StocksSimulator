import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import json
import urllib
import pandas as pd
import sqlite3

# API_KEY pk_767ae94d341d4108b93c22ae5d57f8f4

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
    user_id = session['user_id']
    table = db.execute("SELECT symbol, sum(quantity) as quantity FROM transactions WHERE user_id = :userid GROUP BY symbol ORDER BY symbol;",
                       userid = user_id)
    total = 0
    for row in table:
        stock = lookup(row['symbol'])
        row['name'] = stock['name']
        row['price'] = round(stock['price'], 2)
        row['total'] = round(row['price']*row['quantity'], 2)
        total = round(total + row['total'], 2)

    user = session["user_id"]
    total_cash = db.execute("SELECT cash FROM users WHERE id =:user", user=user)
    cash = round(total_cash[0]['cash'], 2)

    return render_template("index.html", table=table, total=total+cash, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("quote")
        infos = lookup(symbol)
        user = session["user_id"]
        total_cash = db.execute("SELECT cash FROM users WHERE id =:user", user=user)
        cash = total_cash[0]['cash']

        shares = int(request.form.get("shares"))
        total = infos['price'] * shares

        if total > cash:
            return apology("you don't have enough money, poor thing", 405)
        else:
            db.execute("UPDATE users SET cash = :cash WHERE id = :userid", cash=cash-total, userid=user)
            db.execute("INSERT INTO transactions (user_id, symbol, quantity, price) VALUES (:userid, :symbol, :quantity, :price)",
                       userid=user, symbol=infos['symbol'], quantity=shares, price=infos['price'])
            return redirect("/")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session['user_id']
    table = db.execute("SELECT symbol, quantity, price, datetime FROM transactions WHERE user_id = :userid ORDER BY datetime;",
                       userid = user_id)
    for row in table:
        stock = lookup(row['symbol'])
        row['name'] = stock['name']

    return render_template("history.html", table=table)

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

    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("quote")
        infos = lookup(symbol)
        return render_template("quoted.html", companyName=infos["name"], symbol=infos["symbol"], latestPrice=infos["price"])


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    else:
        if not request.form.get("username"):
            return apology("you must provide a username", 403)

        if not request.form.get("password"):
            return apology("you must provide a password", 403)

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username don't exists
        if len(rows) == 1:
            return apology("username already exists", 403)

        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                   username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))

        return redirect("/login")


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "GET":
        return render_template("password.html")
    else:
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if len(rows) != 1:
            return apology("no username matching", 403)
        db.execute("UPDATE users SET hash = :password WHERE username = :username",
                    username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))
        return redirect("/login")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == 'GET':
        user = session['user_id']
        all_stocks = db.execute("SELECT symbol, sum(quantity) as quantity FROM transactions WHERE user_id = :userid GROUP BY symbol ORDER BY symbol;",
                                userid = user)
        stock_list = []
        for row in all_stocks:
            stock_list.append(row['symbol'])
        return render_template("sell.html", stock_list=stock_list)
    else:
        user = session['user_id']

        stock = request.form.get("stocks")
        number_shares = int(request.form.get("shares"))
        price = lookup(stock)['price']
        money = number_shares*price

        db.execute("INSERT INTO transactions (user_id, symbol, quantity, price) VALUES (:userid, :symbol, :quantity, :price)",
                    userid=user, symbol=stock, quantity=(-number_shares), price=price)
        total_cash = db.execute("SELECT cash FROM users WHERE id =:user", user=user)
        cash_before = total_cash[0]['cash']

        db.execute("UPDATE users SET cash = :cash_now WHERE id = :userid", cash_now=cash_before+money, userid=user)

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)