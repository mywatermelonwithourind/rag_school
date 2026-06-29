USE rag_school;

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
