-- LangGraph PostgresSaver 标准建表语句
-- 这些表用于存储对话状态、检查点和持久化数据

-- 1. 检查点表 (Checkpoints)
-- 存储每个步骤的快照信息
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- 2. 检查点数据块表 (Checkpoint Blobs)
-- 存储大型数据对象，避免主表过大
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

-- 3. 检查点写入表 (Checkpoint Writes)
-- 存储待写入的数据或中间状态
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- 索引建议 (优化查询性能)
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON checkpoints (thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id_ns ON checkpoints (thread_id, checkpoint_ns);