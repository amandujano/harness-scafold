package main

import "fmt"

func main() {
	fmt.Println(Greeting())
}

// Greeting returns the application banner.
func Greeting() string {
	return "{{name}}"
}
