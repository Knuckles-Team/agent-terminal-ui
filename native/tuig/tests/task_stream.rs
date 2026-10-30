use tuig_native::{
    correlation::{TaskCorrelation, TaskEvent},
    task_stream::{MAX_EVENT_BYTES, MAX_LINE_BYTES, StreamError, TaskStreamDecoder},
};
use serde_json::{Value, json};

fn task() -> Value {
    json!({"kind":"task", "id":"task-1", "contextId":"ctx-1",
        "metadata":{"arbora":{"runId":"run-1"}}, "status":{"state":"working"}})
}
fn make_decoder() -> TaskStreamDecoder {
    TaskStreamDecoder::new(
        "request-1".into(),
        TaskCorrelation::from_task(&task()).unwrap(),
    )
    .unwrap()
}
fn envelope(result: Value) -> Value {
    json!({"jsonrpc":"2.0","id":"request-1","result":result})
}
fn frame(value: Value, cursor: &str) -> Vec<u8> {
    format!("id: {cursor}\ndata: {value}\n\n").into_bytes()
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.1
#[test]
fn every_utf8_split_and_line_ending_delivers_the_same_correlated_event() {
    let result = json!({"kind":"artifact-update","taskId":"task-1","contextId":"ctx-1",
        "artifact":{"parts":[{"kind":"text","text":"hello 界 🦀"}]}});
    for ending in ["\n", "\r\n", "\r"] {
        let input = format!(
            ": heartbeat{ending}id: opaque:界/42{ending}data: {}{ending}{ending}",
            envelope(result.clone())
        );
        for split in 0..=input.len() {
            let mut decoder = make_decoder();
            let mut events = Vec::new();
            decoder
                .feed(&input.as_bytes()[..split], |e| events.push(e))
                .unwrap();
            decoder
                .feed(&input.as_bytes()[split..], |e| events.push(e))
                .unwrap();
            decoder.finish().unwrap();
            assert_eq!(events.len(), 1);
            assert_eq!(events[0].event, TaskEvent::Text("hello 界 🦀".into()));
            assert_eq!(events[0].cursor.as_deref(), Some("opaque:界/42"));
        }
    }
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.1
#[test]
fn multiline_data_and_id_only_inheritance_do_not_acknowledge_until_valid_data() {
    let mut decoder = make_decoder();
    decoder
        .feed(b"id: pending\n\n", |_| panic!("no data"))
        .unwrap();
    assert_eq!(decoder.cursor(), None);
    let data = format!(
        "data: {{\"jsonrpc\":\"2.0\",\ndata: \"id\":\"request-1\",\"result\":{}}}\n\n",
        task()
    );
    let mut events = Vec::new();
    decoder.feed(data.as_bytes(), |e| events.push(e)).unwrap();
    assert_eq!(decoder.cursor(), Some("pending"));
    decoder
        .feed(format!("data: {}\n\n", envelope(task())).as_bytes(), |e| {
            events.push(e)
        })
        .unwrap();
    assert_eq!(events[1].cursor.as_deref(), Some("pending"));
    decoder
        .feed(&frame(envelope(task()), ""), |e| events.push(e))
        .unwrap();
    assert_eq!(events[2].cursor.as_deref(), Some(""));
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.1
#[test]
fn malformed_envelopes_and_foreign_bindings_never_advance_cursor() {
    let mut foreign = task();
    foreign["contextId"] = json!("foreign");
    let mut foreign_run = task();
    foreign_run["metadata"]["arbora"]["runId"] = json!("foreign");
    for bad in [
        json!({"jsonrpc":"1.0","id":"request-1","result":task()}),
        json!({"jsonrpc":"2.0","id":"other","result":task()}),
        json!({"jsonrpc":"2.0","id":1,"result":task()}),
        json!({"jsonrpc":"2.0","id":"request-1"}),
        json!({"jsonrpc":"2.0","id":"request-1","result":task(),"error":{}}),
        envelope(foreign),
        envelope(foreign_run),
    ] {
        let mut decoder = make_decoder();
        decoder
            .feed(&frame(envelope(task()), "accepted"), |_| {})
            .unwrap();
        assert!(
            decoder
                .feed(&frame(bad, "untrusted"), |_| panic!("invalid event"))
                .is_err()
        );
        assert_eq!(decoder.cursor(), Some("accepted"));
        assert_eq!(
            decoder.feed(&frame(envelope(task()), "later"), |_| panic!("poisoned")),
            Err(StreamError::Stopped)
        );
    }
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.1
#[test]
fn refusal_truncation_invalid_utf8_and_nul_cursor_fail_closed() {
    let mut decoder = make_decoder();
    let refusal = json!({"jsonrpc":"2.0","id":"request-1","error":{"message":"private detail"}});
    assert_eq!(
        decoder.feed(&frame(refusal, "bad"), |_| panic!()),
        Err(StreamError::Refused)
    );
    assert_eq!(decoder.cursor(), None);
    for input in [b"data: \xff\n".as_slice(), b"id: a\0b\n"] {
        let mut decoder = make_decoder();
        assert!(decoder.feed(input, |_| panic!()).is_err());
    }
    let mut partial = make_decoder();
    partial
        .feed(
            format!("data: {}\n", envelope(task())).as_bytes(),
            |_| panic!(),
        )
        .unwrap();
    assert_eq!(partial.finish(), Err(StreamError::Truncated));
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.1
#[test]
fn limits_cover_fragmented_lines_comments_and_unknown_fields() {
    let mut decoder = make_decoder();
    for _ in 0..MAX_LINE_BYTES {
        decoder.feed(b"x", |_| panic!()).unwrap();
    }
    assert_eq!(decoder.feed(b"x", |_| panic!()), Err(StreamError::Limit));
    for prefix in [":", "unknown:"] {
        let mut decoder = make_decoder();
        let line = format!("{prefix}{}\n", "x".repeat(1000));
        let mut bytes = 0;
        loop {
            bytes += line.len();
            if decoder.feed(line.as_bytes(), |_| panic!()).is_err() {
                break;
            }
            assert!(bytes <= MAX_EVENT_BYTES);
        }
        assert!(bytes > MAX_EVENT_BYTES);
        assert_eq!(decoder.cursor(), None);
    }
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.1
#[test]
fn bytewise_bom_and_eof_preserve_only_complete_events() {
    let input = format!("\u{feff}id: cursor\r\ndata: {}\r\n\r\n", envelope(task()));
    let mut decoder = make_decoder();
    let mut events = Vec::new();
    for byte in input.bytes() {
        decoder.feed(&[byte], |e| events.push(e)).unwrap();
    }
    decoder.finish().unwrap();
    assert_eq!(events.len(), 1);
    assert_eq!(decoder.cursor(), Some("cursor"));
    for suffix in ["", "\r", "\r\n"] {
        let mut decoder = make_decoder();
        let input = format!("data: {}{suffix}", envelope(task()));
        decoder
            .feed(input.as_bytes(), |_| panic!("incomplete frame"))
            .unwrap();
        assert_eq!(decoder.finish(), Err(StreamError::Truncated));
        assert_eq!(decoder.cursor(), None);
    }
}
