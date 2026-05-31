from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(128), unique=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    documents = db.relationship(
        "Document", back_populates="owner", cascade="all, delete-orphan"
    )
    categories = db.relationship(
        "Category", back_populates="owner", cascade="all, delete-orphan"
    )

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    owner = db.relationship("User", back_populates="categories")
    children = db.relationship(
        "Category", backref=db.backref("parent", remote_side=[id])
    )
    documents = db.relationship("Document", back_populates="category")


class Publisher(db.Model):
    __tablename__ = "publishers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(256), nullable=False)
    address = db.Column(db.String(256))
    website = db.Column(db.String(256))

    sources = db.relationship("Source", back_populates="publisher")

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_publisher_user_name"),
    )


class Source(db.Model):
    __tablename__ = "sources"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(256), nullable=False, index=True)
    type = db.Column(
        db.Enum("journal", "conference", "book_series", "other", name="source_type"),
        nullable=False,
        default="journal",
    )
    publisher_id = db.Column(db.Integer, db.ForeignKey("publishers.id"), nullable=True)
    issn = db.Column(db.String(20))

    publisher = db.relationship("Publisher", back_populates="sources")
    documents = db.relationship("Document", back_populates="source")

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", "type", name="uq_source_user_name_type"),
    )


class Affiliation(db.Model):
    __tablename__ = "affiliations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(256), nullable=False)
    address = db.Column(db.String(256))

    authors = db.relationship(
        "Author", secondary="author_affiliations", back_populates="affiliations"
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_affiliation_user_name"),
    )


class Author(db.Model):
    __tablename__ = "authors"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(128), nullable=False, index=True)
    code = db.Column(db.SmallInteger, nullable=False, default=1)

    affiliations = db.relationship(
        "Affiliation", secondary="author_affiliations", back_populates="authors"
    )
    document_links = db.relationship(
        "DocumentAuthor", back_populates="author", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", "code", name="uq_author_user_name_code"),
    )

    @property
    def display_name(self) -> str:
        return f"{self.name}#{self.code}"


class AuthorCode(db.Model):
    """Per-(user, name) counter for assigning unique codes to same-name authors."""
    __tablename__ = "author_codes"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), primary_key=True
    )
    name = db.Column(db.String(128), primary_key=True)
    next_code = db.Column(db.SmallInteger, nullable=False, default=2)


class AuthorAffiliation(db.Model):
    __tablename__ = "author_affiliations"

    author_id = db.Column(db.Integer, db.ForeignKey("authors.id"), primary_key=True)
    affiliation_id = db.Column(
        db.Integer, db.ForeignKey("affiliations.id"), primary_key=True
    )


class Keyword(db.Model):
    __tablename__ = "keywords"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(128), nullable=False)

    documents = db.relationship(
        "Document", secondary="document_keywords", back_populates="keywords"
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_keyword_user_name"),
    )


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.id"), nullable=True)

    title = db.Column(db.String(512), nullable=False)
    abstract = db.Column(db.Text)
    document_type = db.Column(
        db.Enum(
            "journal_article",
            "conference_paper",
            "book",
            "thesis",
            "report",
            "other",
            name="document_type",
        ),
        default="journal_article",
        nullable=False,
    )
    publication_year = db.Column(db.SmallInteger)
    volume = db.Column(db.String(32))
    issue = db.Column(db.String(32))
    pages = db.Column(db.String(32))
    doi = db.Column(db.String(128), index=True)
    notes = db.Column(db.Text)
    rating = db.Column(db.SmallInteger)
    reading_status = db.Column(
        db.Enum("unread", "reading", "read", name="reading_status"),
        default="unread",
        nullable=False,
    )
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    owner = db.relationship("User", back_populates="documents")
    category = db.relationship("Category", back_populates="documents")
    source = db.relationship("Source", back_populates="documents")
    author_links = db.relationship(
        "DocumentAuthor",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentAuthor.author_order",
    )
    keywords = db.relationship(
        "Keyword", secondary="document_keywords", back_populates="documents"
    )
    files = db.relationship(
        "File", back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def authors(self):
        return [link.author for link in self.author_links]

    @property
    def authors_display(self) -> str:
        return ", ".join(a.name for a in self.authors)

    @property
    def keywords_display(self) -> str:
        return ", ".join(k.name for k in self.keywords)


class DocumentAuthor(db.Model):
    __tablename__ = "document_authors"

    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("authors.id"), primary_key=True)
    author_order = db.Column(db.SmallInteger, nullable=False, default=1)

    document = db.relationship("Document", back_populates="author_links")
    author = db.relationship("Author", back_populates="document_links")


class DocumentKeyword(db.Model):
    __tablename__ = "document_keywords"

    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), primary_key=True)
    keyword_id = db.Column(db.Integer, db.ForeignKey("keywords.id"), primary_key=True)


class UserSetting(db.Model):
    """Per-user configuration (currently MinerU URL; extend as needed)."""
    __tablename__ = "user_settings"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), primary_key=True
    )
    mineru_url = db.Column(db.String(256))

    user = db.relationship(
        "User",
        backref=db.backref("settings", uselist=False, cascade="all, delete-orphan"),
    )


class AIAgentSetting(db.Model):
    """Per-user screen AI agent configuration."""
    __tablename__ = "ai_agent_settings"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), primary_key=True
    )
    agent_name = db.Column(db.String(64), nullable=False, default="小咪")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    scale = db.Column(db.Float, nullable=False, default=1.0)
    facing = db.Column(db.String(8), nullable=False, default="right")
    position_x = db.Column(db.Integer, nullable=False, default=24)
    position_y = db.Column(db.Integer, nullable=False, default=24)
    api_url = db.Column(db.String(512))
    api_key = db.Column(db.String(512))
    model = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user = db.relationship(
        "User",
        backref=db.backref("ai_agent_setting", uselist=False, cascade="all, delete-orphan"),
    )


class AIAgentActivity(db.Model):
    """Per-user activity log used by the screen AI agent journal."""
    __tablename__ = "ai_agent_activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    event_type = db.Column(db.String(64), nullable=False, index=True)
    label = db.Column(db.String(256), nullable=False)
    metadata_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)

    user = db.relationship(
        "User",
        backref=db.backref("ai_agent_activities", cascade="all, delete-orphan"),
    )


class AIAgentJournal(db.Model):
    """Per-user generated AI journals (daily/weekly) persisted for calendar view."""
    __tablename__ = "ai_agent_journals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    period = db.Column(
        db.Enum("daily", "weekly", name="ai_journal_period"),
        nullable=False,
        index=True,
    )
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=False, index=True)
    title = db.Column(db.String(128), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user = db.relationship(
        "User",
        backref=db.backref("ai_agent_journals", cascade="all, delete-orphan"),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "period", "start_date", name="uq_ai_journal_user_period_start"
        ),
    )


class MergeAudit(db.Model):
    """Persistent audit log for dictionary merge / rollback operations."""
    __tablename__ = "merge_audits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    action = db.Column(
        db.Enum("merge_apply", "merge_rollback", name="merge_audit_action"),
        nullable=False,
    )
    target_audit_id = db.Column(
        db.Integer, db.ForeignKey("merge_audits.id"), nullable=True, index=True
    )
    summary_json = db.Column(db.Text, nullable=False, default="{}")
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    rolled_back_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)

    target_audit = db.relationship("MergeAudit", remote_side=[id], uselist=False)


class File(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False, index=True
    )
    file_path = db.Column(db.String(512), nullable=False)
    original_name = db.Column(db.String(256), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    mime_type = db.Column(db.String(64))
    uploaded_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    document = db.relationship("Document", back_populates="files")
