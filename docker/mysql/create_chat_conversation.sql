USE rag_school;

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
