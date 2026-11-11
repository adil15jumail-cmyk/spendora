import os, json, calendar
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from flask import Flask,render_template,request,redirect,url_for,flash,jsonify,abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager,UserMixin,login_user,logout_user,login_required,current_user
from werkzeug.security import generate_password_hash,check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

app=Flask(__name__); app.config["SECRET_KEY"]=os.getenv("SECRET_KEY","dev-only-change-me")
url = os.getenv("DATABASE_URL", "sqlite:///spendora.db")

if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg://", 1)
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"]=url; app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
db=SQLAlchemy(app); lm=LoginManager(app); lm.login_view="login"

class User(UserMixin,db.Model):
 id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(80),nullable=False)
 email=db.Column(db.String(160),unique=True,nullable=False,index=True); password_hash=db.Column(db.String(255),nullable=False)
 currency=db.Column(db.String(3),default="INR"); timezone=db.Column(db.String(64),default="Asia/Kolkata")
 def set_password(self,p): self.password_hash=generate_password_hash(p)
 def check_password(self,p): return check_password_hash(self.password_hash,p)
class Subscription(db.Model):
 id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True)
 name=db.Column(db.String(120),nullable=False); category=db.Column(db.String(40),default="Other")
 price=db.Column(db.Numeric(12,2),nullable=False); cycle=db.Column(db.String(12),default="monthly")
 billing_day=db.Column(db.Integer,nullable=False); billing_month=db.Column(db.Integer)
 reminder_days=db.Column(db.Integer,default=3); active=db.Column(db.Boolean,default=True)
 notes=db.Column(db.Text,default=""); website_url=db.Column(db.String(500),default="")
 created_at=db.Column(db.DateTime,default=datetime.utcnow)
class PushSubscription(db.Model):
 id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False,index=True)
 endpoint=db.Column(db.Text,unique=True,nullable=False); data=db.Column(db.Text,nullable=False)
class ReminderLog(db.Model):
 id=db.Column(db.Integer,primary_key=True); subscription_id=db.Column(db.Integer,db.ForeignKey("subscription.id"),nullable=False)
 renewal_date=db.Column(db.Date,nullable=False)
 __table_args__=(db.UniqueConstraint("subscription_id","renewal_date",name="uq_reminder"),)
User.subscriptions=db.relationship("Subscription",cascade="all,delete-orphan",backref="owner")
User.push_subscriptions=db.relationship("PushSubscription",cascade="all,delete-orphan",backref="owner")
@lm.user_loader
def load_user(uid): return db.session.get(User,int(uid))
def today(u):
 try:return datetime.now(ZoneInfo(u.timezone)).date()
 except:return date.today()
def next_date(s,start):
 if s.cycle=="yearly":
  m=s.billing_month or start.month
  for y in (start.year,start.year+1):
   d=date(y,m,min(s.billing_day,calendar.monthrange(y,m)[1]))
   if d>=start:return d
 y,m=start.year,start.month
 d=date(y,m,min(s.billing_day,calendar.monthrange(y,m)[1]))
 if d<start:
  m+=1
  if m==13:y,m=y+1,1
  d=date(y,m,min(s.billing_day,calendar.monthrange(y,m)[1]))
 return d
def owned(sid):
 s=db.session.get(Subscription,sid)
 if not s or s.user_id!=current_user.id:abort(404)
 return s
@app.route("/")
def home(): return redirect(url_for("dashboard")) if current_user.is_authenticated else render_template("landing.html")
@app.route("/register",methods=["GET","POST"])
def register():
 if request.method=="POST":
  name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
  if not name or not email or len(pw)<8: flash("Enter your name/email and a password of at least 8 characters.","error")
  elif User.query.filter_by(email=email).first(): flash("That email is already registered.","error")
  else:
   u=User(name=name,email=email);u.set_password(pw);db.session.add(u);db.session.commit();login_user(u);return redirect(url_for("dashboard"))
 return render_template("auth.html",mode="register")
@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":
  u=User.query.filter_by(email=request.form.get("email","").lower().strip()).first()
  if u and u.check_password(request.form.get("password","")):login_user(u);return redirect(url_for("dashboard"))
  flash("Email or password is incorrect.","error")
 return render_template("auth.html",mode="login")
@app.post("/logout")
@login_required
def logout():logout_user();return redirect(url_for("home"))
@app.route("/dashboard")
@login_required
def dashboard():
 items=Subscription.query.filter_by(user_id=current_user.id).order_by(Subscription.created_at.desc()).all()
 active=[s for s in items if s.active]; t=today(current_user)
 upcoming=sorted([(s,next_date(s,t),(next_date(s,t)-t).days) for s in active if (next_date(s,t)-t).days<=7],key=lambda x:x[1])
 monthly=sum(float(s.price)/(12 if s.cycle=="yearly" else 1) for s in active)
 return render_template("dashboard.html",subscriptions=items,active=active,upcoming=upcoming,monthly=monthly)
@app.route("/subscriptions")
@login_required
def subscriptions():return render_template("subscriptions.html",subscriptions=Subscription.query.filter_by(user_id=current_user.id).order_by(Subscription.name).all())
@app.post("/subscriptions/add")
@login_required
def add():
 try:
  name=request.form["name"].strip();price=float(request.form["price"]);cycle=request.form["cycle"];day=int(request.form["billing_day"]);month=int(request.form.get("billing_month") or 1);rem=int(request.form.get("reminder_days",3))
  if not name or price<0 or cycle not in ("monthly","yearly") or not 1<=day<=31 or not 1<=month<=12:raise ValueError()
  db.session.add(Subscription(user_id=current_user.id,name=name,price=price,category=request.form.get("category","Other"),cycle=cycle,billing_day=day,billing_month=month if cycle=="yearly" else None,reminder_days=max(0,min(rem,30)),notes=request.form.get("notes",""),website_url=request.form.get("website_url","")))
  db.session.commit();flash("Subscription added.","success")
 except (ValueError,KeyError):flash("Check your details. Billing day must be 1–31.","error")
 return redirect(url_for("subscriptions"))
@app.post("/subscriptions/<int:sid>/update")
@login_required
def update(sid):
 s=owned(sid)
 try:
  s.name=request.form["name"].strip();s.price=float(request.form["price"]);s.billing_day=int(request.form["billing_day"]);s.reminder_days=int(request.form["reminder_days"]);s.category=request.form.get("category",s.category);s.active=request.form.get("active")=="true"
  if not s.name or s.price<0 or not 1<=s.billing_day<=31:raise ValueError()
  db.session.commit();flash("Subscription updated.","success")
 except ValueError:db.session.rollback();flash("Invalid subscription values.","error")
 return redirect(url_for("subscriptions"))
@app.post("/subscriptions/<int:sid>/delete")
@login_required
def delete(sid):db.session.delete(owned(sid));db.session.commit();flash("Subscription deleted.","success");return redirect(url_for("subscriptions"))
@app.route("/calendar")
@login_required
def calendar_page():
 t=today(current_user);events=[(s,next_date(s,t)) for s in Subscription.query.filter_by(user_id=current_user.id,active=True).all()]
 return render_template("calendar.html",events=sorted(events,key=lambda x:x[1]))
@app.route("/analytics")
@login_required
def analytics():
 subs=Subscription.query.filter_by(user_id=current_user.id,active=True).all();cats={}
 for s in subs:cats[s.category]=cats.get(s.category,0)+float(s.price)/(12 if s.cycle=="yearly" else 1)
 total=sum(cats.values());return render_template("analytics.html",cats=cats,total=total,annual=total*12,average=total/len(subs) if subs else 0)
@app.route("/settings",methods=["GET","POST"])
@login_required
def settings():
 if request.method=="POST":
  c=request.form.get("currency","INR");tz=request.form.get("timezone","Asia/Kolkata")
  if c in ("INR","USD","EUR","GBP","JPY"):current_user.currency=c
  try:ZoneInfo(tz);current_user.timezone=tz
  except:pass
  db.session.commit();flash("Settings saved.","success");return redirect(url_for("settings"))
 return render_template("settings.html")
@app.get("/api/push/key")
@login_required
def push_key():return jsonify(publicKey=os.getenv("VAPID_PUBLIC_KEY",""))
@app.post("/api/push/subscribe")
@login_required
def push_subscribe():
 data=request.get_json(force=True);ep=data.get("endpoint")
 if not ep:return jsonify(error="Missing endpoint"),400
 row=PushSubscription.query.filter_by(endpoint=ep).first()
 if row:row.user_id=current_user.id;row.data=json.dumps(data)
 else:db.session.add(PushSubscription(user_id=current_user.id,endpoint=ep,data=json.dumps(data)))
 db.session.commit();return jsonify(ok=True)
def send_reminders():
 public,private=os.getenv("VAPID_PUBLIC_KEY"),os.getenv("VAPID_PRIVATE_KEY")
 if not public or not private:return
 try:from pywebpush import webpush
 except ImportError:return
 with app.app_context():
  for u in User.query.all():
   t=today(u)
   for s in Subscription.query.filter_by(user_id=u.id,active=True).all():
    renewal=next_date(s,t)
    if t!=renewal-timedelta(days=s.reminder_days) or ReminderLog.query.filter_by(subscription_id=s.id,renewal_date=renewal).first():continue
    payload=json.dumps({"title":"Spendora renewal reminder","body":f"{s.name} renews on {renewal:%d %b %Y}.","url":"/calendar"})
    sent=False
    for p in list(u.push_subscriptions):
     try:webpush(subscription_info=json.loads(p.data),data=payload,vapid_private_key=private,vapid_claims={"sub":os.getenv("VAPID_SUBJECT","mailto:admin@example.com")});sent=True
     except Exception:db.session.delete(p)
    if sent:db.session.add(ReminderLog(subscription_id=s.id,renewal_date=renewal))
  db.session.commit()
with app.app_context():db.create_all()
if os.getenv("ENABLE_SCHEDULER","true").lower()=="true":
 scheduler=BackgroundScheduler(daemon=True);scheduler.add_job(send_reminders,"interval",minutes=30,id="renewals",replace_existing=True);scheduler.start()
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=os.getenv("FLASK_DEBUG")=="1")
