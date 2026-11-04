package main

import "testing"

func TestGreetingReturnsProjectName(t *testing.T) {
	if got := Greeting(); got != "{{name}}" {
		t.Fatalf("Greeting() = %q", got)
	}
}
