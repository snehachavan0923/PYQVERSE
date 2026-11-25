from app.models.academic import (
    AcademicScheme,
    Branch,
    BranchSubjectOffering,
    College,
    ElectiveBasket,
    ElectiveOption,
    Semester,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.ai import AIInteraction
from app.models.learning import (
    BankQuestion,
    Difficulty,
    ExamAnswer,
    ExamAttempt,
    ExamAttemptStatus,
    MockExam,
    MockExamQuestion,
    PracticeAttempt,
    QuestionBookmark,
    QuestionType,
)
from app.models.document import PermissionStatus, QuestionPaper, UploadedDocument
from app.models.progress import Bookmark, QuizAttempt, StudentProgress, StudentTopicActivity
from app.models.resource import LearningResource, ResourceType
from app.models.question import (
    ContentReview,
    DocumentPage,
    Question,
    QuestionOccurrence,
    QuestionTopicMap,
    Solution,
)
from app.models.syllabus import Subtopic, SyllabusDocument, SyllabusVersion, Topic, Unit
from app.models.user import AccountStatus, User, UserRole
from app.models.bootstrap import AdministratorBootstrapRecord