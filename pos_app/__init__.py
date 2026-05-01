import os

import click
from dotenv import load_dotenv
from flask import Flask

from .extensions import db, login_manager
from .models import User, ShopSetting, seed_initial_data
from .routes import main_bp
from .utils import format_money


def create_app():
    load_dotenv()
    app = Flask(__name__)

    # Ensure the instance folder exists for the SQLite database
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-in-production")
    
    # Use instance folder for the local SQLite database
    db_path = os.path.join(app.instance_path, "pos_system.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", f"sqlite:///{db_path}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"
    login_manager.login_message_category = "warning"

    app.jinja_env.filters["money"] = format_money

    app.register_blueprint(main_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_shop_settings():
        setting = ShopSetting.query.first()
        if not setting:
            # Create default setting if it doesn't exist
            setting = ShopSetting(
                shop_name="JP SUPER CENTER",
                address="Front of General Hospital, Ampara",
                phone="+94 712247385",
                bill_message="Thank you for shopping with us."
            )
            db.session.add(setting)
            db.session.commit()
        return dict(shop_settings=setting)

    @app.cli.command("init-db")
    @click.option("--seed", is_flag=True, help="Seed sample data and default admin account.")
    def init_db_command(seed):
        db.create_all()
        if seed:
            seed_initial_data()
        click.echo("Database initialized successfully.")

    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            seed_initial_data()

    return app
