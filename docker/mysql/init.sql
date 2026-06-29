-- 计算机学院智能问答系统 — MySQL 初始化脚本
-- 父块全文 + FAQ 规则 + FAQ 别名

USE rag_school;

-- ---------------------------------------------------------------------------
-- 知识库文件表（文件级元数据 / 入库状态）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_document (
    doc_id          VARCHAR(64)  NOT NULL PRIMARY KEY COMMENT '文档 ID，和 parent_chunk.doc_id 对齐',
    kb_id           VARCHAR(64)  NOT NULL DEFAULT 'kb_cs_college' COMMENT '知识库 ID',
    title           VARCHAR(512) NOT NULL COMMENT '文档标题 / 文件名主体',
    source_name     VARCHAR(512) NOT NULL COMMENT '原始文件名',
    file_ext        VARCHAR(16)  NOT NULL COMMENT '文件扩展名',
    source_type     ENUM('upload', 'directory') NOT NULL DEFAULT 'upload' COMMENT '来源类型',
    source_path     VARCHAR(1024) NULL COMMENT '目录入库时的源路径，上传文件可为空',
    content_chars   INT          NOT NULL DEFAULT 0 COMMENT '清洗后文本字符数',
    parent_count    INT          NOT NULL DEFAULT 0 COMMENT '父块数量',
    child_count     INT          NOT NULL DEFAULT 0 COMMENT '子块数量',
    vector_count    INT          NOT NULL DEFAULT 0 COMMENT '成功写入 Milvus 的子向量数量',
    status          ENUM('ready', 'partial', 'failed') NOT NULL DEFAULT 'ready' COMMENT '入库状态',
    warnings        JSON         NULL COMMENT '解析或向量写入提醒',
    metadata        JSON         NULL COMMENT '扩展元数据',
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_kb_document_kb_updated (kb_id, updated_at),
    INDEX idx_kb_document_source_name (source_name(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库文件表';

-- ---------------------------------------------------------------------------
-- 父块表（全文存储，检索聚合后展示 / FAQ 直出）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parent_chunk (
    parent_chunk_id   VARCHAR(64)  NOT NULL PRIMARY KEY COMMENT '父块唯一 ID',
    content           MEDIUMTEXT   NOT NULL COMMENT '父块全文',
    doc_id            VARCHAR(64)  NOT NULL COMMENT '来源文档 ID',
    kb_id             VARCHAR(64)  NOT NULL DEFAULT 'kb_cs_college' COMMENT '知识库 ID',
    chunk_index       INT          NOT NULL DEFAULT 0 COMMENT '文档内序号',
    title             VARCHAR(512) NULL COMMENT '段落/章节标题',
    metadata          JSON         NULL COMMENT '扩展元数据',
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FULLTEXT INDEX ft_content (content) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='父块全文表';

-- ---------------------------------------------------------------------------
-- FAQ 规则表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS faq_rule (
    faq_id                    VARCHAR(64)  NOT NULL PRIMARY KEY COMMENT 'FAQ 规则 ID',
    standard_question         VARCHAR(512) NOT NULL COMMENT '标准问法',
    target_parent_chunk_ids   JSON         NOT NULL COMMENT '命中后关联的 parent_chunk_id 列表',
    answer_mode               ENUM('llm_generate', 'template', 'parent_chunk_direct')
                              NOT NULL DEFAULT 'parent_chunk_direct' COMMENT '回答模式',
    template_answer           TEXT         NULL COMMENT 'template 模式下的固定回答',
    priority                  INT          NOT NULL DEFAULT 0 COMMENT '优先级，越大越优先',
    enabled                   TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_at                TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='FAQ 规则表';

-- ---------------------------------------------------------------------------
-- FAQ 别名表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS faq_alias (
    alias_id      BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    faq_id        VARCHAR(64)  NOT NULL COMMENT '关联 faq_rule.faq_id',
    alias_text    VARCHAR(512) NOT NULL COMMENT '别名/变体问法',
    match_type    ENUM('exact', 'contains', 'regex')
                  NOT NULL DEFAULT 'contains' COMMENT '匹配方式',
    enabled       TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_faq_id (faq_id),
    INDEX idx_alias (alias_text(191)),
    CONSTRAINT fk_faq_alias_rule FOREIGN KEY (faq_id) REFERENCES faq_rule(faq_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='FAQ 别名表';

-- ---------------------------------------------------------------------------
-- 对话记录表（一轮问答一条记录）
-- ---------------------------------------------------------------------------
-- 已运行的库可手动执行:
-- docker exec -i rag-mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < docker/mysql/create_chat_conversation.sql
CREATE TABLE IF NOT EXISTS chat_conversation (
    id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(64)  NOT NULL COMMENT '会话 ID，作为后端加载上下文的钥匙',
    question      TEXT         NOT NULL COMMENT '本轮用户问题',
    answer        MEDIUMTEXT   NOT NULL COMMENT '本轮助手完整回答',
    query_intent  VARCHAR(32)  NULL COMMENT '本轮路由意图',
    citations     JSON         NULL COMMENT '本轮引用出处快照',
    debug_trace   JSON         NULL COMMENT '本轮调试轨迹快照',
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_chat_conversation_session_created (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='对话记录表';

-- ---------------------------------------------------------------------------
-- 示例数据（联调用）
-- ---------------------------------------------------------------------------
INSERT INTO parent_chunk (parent_chunk_id, content, doc_id, kb_id, chunk_index, title) VALUES
('pc_office_hours', '计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。', 'doc_admin_guide', 'kb_cs_college', 0, '办公时间'),
('pc_counselor_contact', '本科生辅导员联系方式请参见学院官网「学生工作」栏目，或拨打学院办公室总机转接。', 'doc_student_affairs', 'kb_cs_college', 0, '辅导员联系'),
('pc_graduation_req', '计算机专业毕业学分要求为 160 学分，其中必修 98 学分，选修不少于 42 学分。', 'doc_curriculum', 'kb_cs_college', 0, '毕业学分');

INSERT INTO faq_rule (faq_id, standard_question, target_parent_chunk_ids, answer_mode, priority) VALUES
('faq_001', '计算机学院办公时间是什么', '["pc_office_hours"]', 'parent_chunk_direct', 10),
('faq_002', '如何联系辅导员', '["pc_counselor_contact"]', 'template', 10);

INSERT INTO faq_alias (faq_id, alias_text, match_type) VALUES
('faq_001', '上班时间', 'contains'),
('faq_001', '几点上班', 'contains'),
('faq_002', '辅导员电话', 'contains'),
('faq_002', '辅导员联系方式', 'contains');
